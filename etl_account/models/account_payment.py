# -*- coding: utf-8 -*-
#############################################################################
#
#    Steigend IT Solutions.
#
#    Copyright (C) 2023-TODAY Steigend IT Solutions.
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import string
from datetime import datetime
import requests
import json
import qrcode
import base64
from io import BytesIO
from cgitb import reset

class BatchPayment(models.Model):
    _inherit = 'account.batch.payment'
    _description = 'Batch Payment'
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            args += [('branch_id', 'in', branches_ids)]
        return super(BatchPayment, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'allowed_branch_ids' in self._context:
            branches_ids = self._context['allowed_branch_ids']
        else:
            branches_ids = self.env.user.branch_ids.ids
        domain += [('branch_id', 'in', branches_ids)]
        return super(BatchPayment, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    @api.model
    def default_get(self, default_fields):
        res = super(BatchPayment, self).default_get(default_fields)
        if 'default_batch_type' in self._context and self._context['default_batch_type'] == 'inbound':
            payment_method_ids = self.env['account.payment.method'].search([
                ('payment_type', '=', 'inbound'),
                ('code', '=', 'batch_payment')
                ])
            res.update({
                'payment_method_id' : payment_method_ids[0].id,
                })
        res.update({'branch_id': self.env.user.branch_id.id})
        return res
    
    def action_correction(self):
        for payment in self.payment_ids:
            payment.date = self.date
        return True
    
    def action_draft(self):
        for payment in self.payment_ids:
            payment.with_context(batch_payment=True).action_draft()
            payment.payment_line_ids.unlink()
        return True
    
    def action_validate(self):
        payment_obj = self.env['account.payment']
        payment_line_obj = self.env['account.payment.line']
        if self.journal_id.type == 'cash':
            payment_method_line_ids = [line.id for line in self.journal_id.inbound_payment_method_line_ids]
        else:
            payment_method_line_ids = [line.id for line in self.journal_id.inbound_payment_method_line_ids if line.payment_method_id.code == 'batch_payment']
        for line in self.line_ids:
            payment_vals = {
                'payment_type': 'inbound',
                'partner_id': line.partner_id.id,
                'journal_id': self.journal_id.id,
                'amount': line.amount,
                'payment_method_line_id': payment_method_line_ids[0],
                'date': self.date,
                'batch_payment_id': self.id
                }
            if line.account_payment_id:
                line.account_payment_id.write(payment_vals)
                payment = line.account_payment_id
            else:
                payment = payment_obj.create(payment_vals)
            for payment_line in line.line_ids:
                if payment_line.select_ok:
                    payment_line_obj.create({
                        'payment_id': payment.id,
                        'move_id': payment_line.move_id.id,
                        'move_line_id': payment_line.move_line_id.id,
                        'amount_balance': payment_line.amount_balance,
                        'select_ok': payment_line.select_ok
                        })
                else:
                    payment_line.unlink()
                line.account_payment_id = payment.id
            payment.with_context(batch_payment=True).action_post()
        self.validate_batch_button()
        # self.create_counter_entry()
        return True
    
    def check_payments_for_errors(self):
        """ Goes through all the payments of the batches contained in this
        record set, and returns the ones that would impeach batch validation,
        in such a way that the payments impeaching validation for the same reason
        are grouped under a common error message. This function is a hook for
        extension for modules making a specific use of batch payments, such as SEPA
        ones.

        :return:    A list of dictionaries, each one corresponding to a distinct
                    error and containing the following keys:
                    - 'title': A short name for the error (mandatory)
                    - 'records': The recordset of payments facing this error (mandatory)
                    - 'help': A help text to give the user further information
                              on how to solve the error (optional)
        """
        self.ensure_one()
        #We first try to post all the draft batch payments
        rslt = self._check_and_post_draft_payments(self.payment_ids.filtered(lambda x: x.state == 'draft'))

        wrong_state_payments = self.payment_ids.filtered(lambda x: x.state != 'posted')

        if wrong_state_payments:
            rslt.append({
                'title': _("Payments must be posted to be added to a batch."),
                'records': wrong_state_payments,
                'help': _("Set payments state to \"posted\".")
            })

        if self.batch_type == 'outbound':
            not_allowed_payments = self.payment_ids.filtered(lambda x: x.partner_bank_id and not x.partner_bank_id.allow_out_payment)
            if not_allowed_payments:
                rslt.append({
                    'code': 'out_payment_not_allowed',
                    'title': _("Some recipient accounts do not allow out payments."),
                    'records': not_allowed_payments,
                    'help': _("Target another recipient account or allow sending money to the current one.")
                })

        sent_payments = self.payment_ids.filtered(lambda x: x.is_move_sent)
        if sent_payments:
            rslt.append({
                'title': _("Some payments have already been sent."),
                'records': sent_payments,
            })

        if self.batch_type == 'inbound':
            pmls = self.journal_id.inbound_payment_method_line_ids
            default_payment_account = self.journal_id.company_id.account_journal_payment_debit_account_id
        else:
            pmls = self.journal_id.outbound_payment_method_line_ids
            default_payment_account = self.journal_id.company_id.account_journal_payment_credit_account_id
        pmls = pmls.filtered(lambda x: x.payment_method_id == self.payment_method_id)
        no_statement_reconciliation = self.journal_id.default_account_id == (pmls.payment_account_id[:1] or default_payment_account)
        bank_reconciled_payments = self.journal_id.code == 'bank' and self.payment_ids.filtered(lambda x: x.is_matched) or []
        if bank_reconciled_payments and not no_statement_reconciliation:
            rslt.append({
                'title': _("Some payments have already been matched with a bank statement."),
                'records': bank_reconciled_payments,
            })

        return rslt
    
    @api.depends('payment_ids.move_id.is_move_sent', 'payment_ids.is_matched')
    def _compute_state(self):
        for batch in self:
            if batch.payment_ids and all(pay.is_matched and pay.is_move_sent for pay in batch.payment_ids):
                batch.state = 'reconciled'
            elif batch.payment_ids and all(pay.is_move_sent for pay in batch.payment_ids):
                batch.state = 'sent'
            else:
                batch.state = 'draft'
    
    
    @api.depends('currency_id', 'payment_ids.amount', 'payment_ids.amount', 'line_ids', 'line_ids.amount', 'validated')
    def _compute_from_payment_ids(self):
        for batch in self:
            amount_currency = 0.0
            amount_residual = 0.0
            amount_residual_currency = 0.0
            if batch.payment_ids:
                for payment in batch.payment_ids:
                    liquidity_lines, _counterpart_lines, _writeoff_lines = payment._seek_for_lines()
                    for line in liquidity_lines:
                        amount_currency += line.amount_currency
                        amount_residual += line.amount_residual
                        amount_residual_currency += line.amount_residual_currency
            elif batch.line_ids:
                for payment in batch.line_ids:
                    amount_currency += payment.amount
            batch.amount_residual = amount_residual
            batch.amount = amount_currency
            batch.amount_residual_currency = amount_residual_currency
    
    line_ids = fields.One2many('batch.payment.line', 'payment_id', 'Lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Validated'),
        ('reconciled', 'Reconciled'),
        ], store=True, compute='_compute_state', default='draft', tracking=True)
    amount_residual = fields.Monetary(
        currency_field='company_currency_id',
        compute='_compute_from_payment_ids',
        store=True)
    amount_residual_currency = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_from_payment_ids',
        store=True)
    amount = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_from_payment_ids',
        store=True)
    validated = fields.Boolean('Validated')
    payment_method_id = fields.Many2one(
        comodel_name='account.payment.method',
        string='Payment Method', store=True, readonly=True,
        compute='_compute_payment_method_id')
    branch_id = fields.Many2one('res.branch', "Branch")
    bank_date = fields.Date('Bank Date')
    
    @api.depends('batch_type', 'journal_id', 'payment_ids')
    def _compute_payment_method_id(self):
        for batch in self:
            payment_method_ids = self.env['account.payment.method'].search([
                ('payment_type', '=', batch.batch_type),
                ('code', '=', 'batch_payment')
                ])
            batch.payment_method_id = payment_method_ids and payment_method_ids[0].id or False
                
class BatchPaymentLine(models.Model):
    _name = 'batch.payment.line'
    _description = 'Batch Payment Line'
    
    @api.onchange('partner_id')
    def onchange_partner_id(self):
        apls = self.env['batch.payment.customer.line']
        amls = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('move_id.state', '=', 'posted'),
            ('amount_residual', '!=', 0), 
            ('account_id.reconcile', '=', True),
            ('account_id.account_type', '=', 'asset_receivable'), 
            ('account_id.non_trade', '=', False),
            ('debit', '>', 0)
            ], order='date')
        for aml in amls:
            apls += apls.new({
                'move_id': aml.move_id.id,
                'move_line_id': aml.id,
                'amount_balance': aml.amount_residual,
                })
        self.line_ids = apls
    
    @api.depends('line_ids', 'line_ids.select_ok')
    def _compute_amount_selected(self):
        for payment in self:
            payment.amount_selected = sum([line.amount_balance for line in payment.line_ids if line.select_ok])
            
    payment_id = fields.Many2one('account.batch.payment', 'Batch Payment')
    partner_id = fields.Many2one('res.partner', 'Customer')
    amount = fields.Float('Amount')
    line_ids = fields.One2many('batch.payment.customer.line', 'line_id', 'Lines')
    account_payment_id = fields.Many2one('account.payment', 'Payment')
    amount_selected = fields.Float('Selected Amount', compute='_compute_amount_selected', store=True)

class BatchPaymentCustomerLine(models.Model):
    _name = 'batch.payment.customer.line'
    _description = 'Batch Payment Customer Line'
    
    def _incoice_details(self):
        for line in self:
            line.name = line.move_id.name
            line.invoice_date = line.move_id.invoice_date or line.move_id.date
    
    line_id = fields.Many2one('batch.payment.line', 'Payment Line')
    move_id = fields.Many2one('account.move', 'JE')
    move_line_id = fields.Many2one('account.move.line', 'AML')
    amount_balance = fields.Float('Balance Amount')
    select_ok = fields.Boolean('Select')
    name = fields.Char('Invoice Number', compute='_incoice_details')
    invoice_date = fields.Date('Invoice Date', compute='_incoice_details')
    
class AccountPayment(models.Model):
    _inherit = 'account.payment'
    _order = 'date desc, name desc'
    
    payment_line_ids = fields.One2many('account.payment.line', 'payment_id', 'Payment Lines')
    batch_payment_id = fields.Many2one('account.batch.payment', 'Batch Payment')
    amount_selected = fields.Float('Selected Amount', compute='_compute_amount_selected', store=True)
    trans_type = fields.Selection([
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
        ], 'Transaction Type')
    inst_no = fields.Char('Instrument #')
    inst_date = fields.Date('Instrument Date')
    
    @api.depends('payment_line_ids', 'payment_line_ids.select_ok')
    def _compute_amount_selected(self):
        for payment in self:
            payment.amount_selected = sum([line.amount_balance for line in payment.payment_line_ids if line.select_ok])
    
    def write(self, vals):
        if 'branch_id' in vals:
            self.move_id.branch_id = vals['branch_id']
        return super(AccountPayment, self).write(vals)
    
    def action_draft(self):
        for payment in self:
            payment.move_id.posted_before = False
            payment.move_id.name = '/'
            if payment.batch_payment_id and not 'batch_payment' in self._context:
                raise UserError('Batch Payments cannot Reset from this screen')
            if payment.paired_internal_transfer_payment_id:
                paired_payment = payment.paired_internal_transfer_payment_id
                payment.paired_internal_transfer_payment_id = False
                self._cr.execute('delete from account_move where id=%s'% (paired_payment.move_id.id))
                self._cr.execute('delete from account_payment where id=%s'% (paired_payment.id))
        return super(AccountPayment, self).action_draft()
    
    @api.model_create_multi
    def create(self, vals_list):
        payment = super(AccountPayment, self).create(vals_list)
        if not payment.payment_line_ids:
            apl_obj = self.env['account.payment.line']
            aml_obj = self.env['account.move.line']
            if payment.payment_type == 'inbound':
                amls = aml_obj.search([
                    ('partner_id', '=', payment.partner_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('amount_residual', '!=', 0), 
                    ('account_id.reconcile', '=', True),
                    ('account_id.account_type', '=', 'asset_receivable'), 
                    ('account_id.non_trade', '=', False),
                    ('debit', '>', 0)
                    ], order='date')
                for aml in amls:
                    apl_obj.create({
                        'move_id': aml.move_id.id,
                        'move_line_id': aml.id,
                        'amount_balance': aml.amount_residual,
                        'payment_id': payment.id
                        })
            elif payment.payment_type == 'outbound':
                amls = aml_obj.search([
                    ('partner_id', '=', payment.partner_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('amount_residual', '!=', 0), 
                    ('account_id.reconcile', '=', True),
                    ('account_id.account_type', '=', 'liability_payable'), 
                    ('account_id.non_trade', '=', False),
                    ('credit', '>', 0)
                    ], order='date')
                for aml in amls:
                    apl_obj.create({
                        'move_id': aml.move_id.id,
                        'move_line_id': aml.id,
                        'amount_balance': abs(aml.amount_residual),
                        'payment_id': payment.id
                        })
        return payment
    
    @api.onchange('partner_id', 'payment_type')
    def onchange_partner_id(self):
        apls = self.env['account.payment.line']
        aml_obj = self.env['account.move.line']
        if self.partner_id:
            if self.payment_type == 'inbound':
                amls = aml_obj.search([
                    ('partner_id', '=', self.partner_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('amount_residual', '!=', 0), 
                    ('account_id.reconcile', '=', True),
                    ('account_id.account_type', '=', 'asset_receivable'), 
                    ('account_id.non_trade', '=', False),
                    ('debit', '>', 0)
                    ], order='date')
                for aml in amls:
                    apls += apls.new({
                        'move_id': aml.move_id.id,
                        'move_line_id': aml.id,
                        'amount_balance': aml.amount_residual,
                        })
                self.payment_line_ids = apls
            elif self.payment_type == 'outbound':
                amls = aml_obj.search([
                    ('partner_id', '=', self.partner_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('amount_residual', '!=', 0), 
                    ('account_id.reconcile', '=', True),
                    ('account_id.account_type', '=', 'liability_payable'), 
                    ('account_id.non_trade', '=', False),
                    ('credit', '>', 0)
                    ], order='date')
                for aml in amls:
                    apls += apls.new({
                        'move_id': aml.move_id.id,
                        'move_line_id': aml.id,
                        'amount_balance': abs(aml.amount_residual),
                        })
                self.payment_line_ids = apls
        else:
            self.payment_line_ids = False
    
    def action_post(self):
        for payment in self:
            payment.outstanding_account_id = payment.journal_id.default_account_id.id
            payment.move_id.branch_id = payment.branch_id.id
            for move_line in payment.move_id.line_ids:
                if not move_line.account_id.active:
                    move_line.account_id  = payment.journal_id.default_account_id.id
        res = super(AccountPayment, self).action_post()
        amls = []
        for payment in self:
            if payment.batch_payment_id and not 'batch_payment' in self._context:
                raise UserError('Batch Payments cannot Post from this screen')
            if not payment.is_internal_transfer:
                if payment.payment_type == 'inbound':
                    for line in payment.payment_line_ids:
                        if line.select_ok:
                            amls.append(line.move_line_id.id)
                        else:
                            line.unlink()
                    for line in payment.line_ids:
                        if line.account_id.account_type == 'asset_receivable':
                            amls.append(line.id)
                elif payment.payment_type == 'outbound':
                    for line in payment.payment_line_ids:
                        if line.select_ok:
                            amls.append(line.move_line_id.id)
                        else:
                            line.unlink()
                    for line in payment.line_ids:
                        if line.account_id.account_type == 'liability_payable':
                            amls.append(line.id) 
        if amls:
            self.env['account.move.line'].browse(amls).reconcile()
        return res
        
class AccountPaymentLine(models.Model):
    _name = 'account.payment.line'
    _description = 'Account Payment Lines'
    
    def _incoice_details(self):
        for line in self:
            line.name = line.move_id.name
            line.invoice_date = line.move_id.invoice_date or line.move_id.date
            
    payment_id = fields.Many2one('account.payment', 'Payment')
    move_id = fields.Many2one('account.move', 'JE')
    move_line_id = fields.Many2one('account.move.line', 'AML')
    amount_balance = fields.Float('Balance Amount')
    select_ok = fields.Boolean('Select')
    name = fields.Char('Invoice Number', compute='_incoice_details')
    invoice_date = fields.Date('Invoice Date', compute='_incoice_details')
    
    