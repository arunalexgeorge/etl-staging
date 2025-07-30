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

from odoo import _, api, fields, models, Command, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang, xlwt
from io import BytesIO
import base64
         
class BankRenconcile(models.TransientModel):
    _inherit = 'res.config.settings'
    _name = 'bank.reconcile'
    _description = 'Bank Reconcile' 
    
    @api.model
    def default_get(self, def_fields):
        res = super(BankRenconcile, self).default_get(def_fields)
        if 'deafult_journal_id' in self._context:
            res['journal_id'] = self._context['active_id']
            res['date'] = fields.Date.context_today(self)
        else:
            company = self.env['res.company'].browse(1)
            res['date'] = company.last_reconciled_date
            res['journal_id'] = company.last_reconciled_journal_id and company.last_reconciled_journal_id.id or False
        return res
    
    date = fields.Date('Date')
    journal_id = fields.Many2one('account.journal', 'Account')
    ledger_balance = fields.Float('Ledger Balance')
    bank_balance = fields.Float('Balance as per Bank')
    unrec_balance = fields.Float('Not Reflected in Bank')
    line_ids = fields.One2many('bank.reconcile.line', 'reconcile_id', 'Lines')
    batch_line_ids = fields.One2many('bank.reconcile.line', 'batch_reconcile_id', 'Batch Lines')
    name = fields.Char('Description')
    
    def action_reconcile(self):
        for line in self.line_ids:
            if line.bank_date:
                self._cr.execute("""update account_move_line set bank_date='%s' where id=%s"""% (line.bank_date, line.move_line_id.id))
                self._cr.execute("""update account_move set bank_date='%s' where id=%s"""% (line.bank_date, line.move_line_id.move_id.id))
            else:
                self._cr.execute("""update account_move_line set bank_date=NULL where id=%s"""% (line.move_line_id.id))
                self._cr.execute("""update account_move set bank_date=NULL where id=%s"""% (line.move_line_id.move_id.id))
        for line in self.batch_line_ids:
            move_line_ids = []
            move_ids = []
            move_lines = self.env['account.move.line'].search([('payment_id.batch_payment_id', '=', line.batch_payment_id.id)])
            for move_line in move_lines:
                move_ids.append(move_line.move_id.id)
                if move_line.account_id.id == self.journal_id.default_account_id.id:
                    move_line_ids.append(move_line.id)
            if line.bank_date:
                if move_line_ids:
                    for move_line_id in move_line_ids:
                        self._cr.execute("""update account_move_line set bank_date='%s' where id=%s"""% (line.bank_date, move_line_id))
                if move_ids:
                    for move_id in move_ids:
                        self._cr.execute("""update account_move set bank_date='%s' where id=%s"""% (line.bank_date, move_id))
                if line.batch_payment_id.id:
                    self._cr.execute("""update account_batch_payment set bank_date='%s' where id=%s"""% (line.bank_date, line.batch_payment_id.id))
                    self._cr.execute("""update account_batch_payment set state='reconciled' where id=%s"""% (line.batch_payment_id.id))
            else:
                if move_line_ids:
                    for move_line_id in move_line_ids:
                        self._cr.execute("""update account_move_line set bank_date=NULL where id=%s"""% (move_line_id))
                if move_ids:
                    for move_id in move_ids:
                        self._cr.execute("""update account_move set bank_date=NULL where id=%s"""% (move_id))
                if line.batch_payment_id.id:
                    self._cr.execute("""update account_batch_payment set bank_date=NULL where id=%s"""% (line.batch_payment_id.id))
                    self._cr.execute("""update account_batch_payment set state='sent' where id=%s"""% (line.batch_payment_id.id))
        self.env['res.company'].browse(1).write({
            'last_reconciled_journal_id': self.journal_id.id,
            'last_reconciled_date': self.date
            })
        self.date = False
        self.line_ids.unlink()
        self.batch_line_ids.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            }
    
    @api.onchange('journal_id', 'date')
    def onchange_journal(self):
        lines = self.env['bank.reconcile.line']
        batch_lines = self.env['bank.reconcile.line']
        aml_obj = self.env['account.move.line']
        gl_balance, bank_balance, unrec_total = 0.0, 0.0, 0.0
        if self.date and self.journal_id:
            amls = aml_obj.with_context(no_filter=True).search([
                ('account_id', '=', self.journal_id.default_account_id.id),
                ('date', '<=', self.date),
                '|', ('bank_date', '=', False),
                ('bank_date', '>=', self.date),
                ('move_id.state', '=', 'posted')
                ], order='date')
            for aml in amls:
                if aml.payment_id:
                    if not aml.payment_id.batch_payment_id:
                        if aml.debit > 0 or aml.credit > 0:
                            lines += lines.new({
                                'move_line_id': aml.id,
                                'bank_date': aml.bank_date
                                })
                else:
                    if aml.debit > 0 or aml.credit > 0:
                        lines += lines.new({
                            'move_line_id': aml.id,
                            'bank_date': aml.bank_date
                            })
            batch_payments = self.env['account.batch.payment'].with_context(no_filter=True).search([
                ('journal_id', '=', self.journal_id.id),
                ('date', '<=', self.date),
                '|', ('bank_date', '=', False),
                ('bank_date', '>=', self.date),
                ('state', '!=', 'draft')
                ], order='date')
            for batch_payment in batch_payments:
                batch_lines += batch_lines.new({
                    'batch_payment_id': batch_payment.id,
                    'bank_date': batch_payment.bank_date
                    })
            self.line_ids = lines
            self.batch_line_ids = batch_lines
            amls = aml_obj.with_context(no_filter=True).search([
                ('account_id', '=', self.journal_id.default_account_id.id),
                ('date', '<=', self.date),
                ('move_id.state', '=', 'posted')
                ])
            gl_balance = round(sum([aml.debit-aml.credit for aml in amls]), 3)
            unrec_amls = aml_obj.with_context(no_filter=True).search([
                ('account_id', '=', self.journal_id.default_account_id.id),
                ('date', '<=', self.date),
                ('move_id.state', '=', 'posted'),
                '|', ('bank_date', '=', False),
                ('bank_date', '>', self.date),
                ])
            for aml in unrec_amls:
                unrec_total += aml.credit - aml.debit
            bank_balance = round(gl_balance, 3) + round(unrec_total, 3)
        self.ledger_balance = gl_balance
        self.bank_balance = bank_balance
        self.unrec_balance = unrec_total
        if self.journal_id:
            self.name = self.journal_id.name
        else:
            self.name = 'Bank Reconciliation'
    
class BankRenconcileLine(models.TransientModel):
    _name = 'bank.reconcile.line'
    _description = 'Bank Reconcile Line'
    
    @api.depends('move_line_id', 'reconcile_id.date', 'reconcile_id.journal_id', 'batch_payment_id')
    def _compute_aml_details(self):
        for line in self:
            if line.move_line_id:
                ml = line.move_line_id
                move = ml.move_id
                voucher_type = 'jv'
                inst_no = ''
                inst_date = False
                trans_type = 'none'
                if move.payment_id:
                    payment = move.payment_id
                    if payment.is_internal_transfer:
                        voucher_type = 'contra'
                    elif payment.payment_type == 'inbound':
                        voucher_type = 'receipt'
                    elif payment.payment_type == 'outbound':
                        voucher_type = 'payment'
                    inst_no = payment.inst_no
                    inst_date = payment.inst_date
                    trans_type = payment.trans_type
                line.date = ml.date
                line.debit = ml.debit
                line.credit = ml.credit
                line.voucher_no = move.name
                line.inst_no = inst_no
                line.inst_date = inst_date
                line.trans_type = trans_type
                name = ml.partner_id and ml.partner_id.name or False
                if not name:
                    name = move.ref or False
                if not name:
                    name = move.name
                line.name = name
                line.voucher_type = voucher_type
                
            elif line.batch_payment_id:
                ml = line.batch_payment_id 
                line.date = ml.date
                line.debit = ml.batch_type == 'inbound' and ml.amount or 0.0
                line.credit = ml.batch_type == 'outbound' and ml.amount or 0.0
                line.voucher_no = ml.name
                line.inst_no = ''
                line.inst_date = ''
                line.name = ml.name
                line.trans_type = 'none'
                line.voucher_type = ml.batch_type == 'inbound' and 'receipt' or 'payment'
            
    date = fields.Date('Date', compute='_compute_aml_details', store=True)
    debit = fields.Float('Debit', compute='_compute_aml_details', store=True)
    credit = fields.Float('Credit', compute='_compute_aml_details', store=True)
    name = fields.Char('Particulars', compute='_compute_aml_details', store=True)
    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ('contra', 'Contra'),
        ('jv', 'JV'),
        ], 'Voucher Type', compute='_compute_aml_details', store=True)
    voucher_no = fields.Char('Voucher #', compute='_compute_aml_details', store=True)
    trans_type = fields.Selection([
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
        ('none', ' ')
        ], 'Transaction Type', compute='_compute_aml_details', store=True)
    inst_no = fields.Char('Instrument #', compute='_compute_aml_details', store=True)
    inst_date = fields.Date('Instrument Date', compute='_compute_aml_details', store=True)
    bank_date = fields.Date('Bank Date')
    move_line_id = fields.Many2one('account.move.line', 'AML')
    batch_payment_id = fields.Many2one('account.batch.payment', 'Batch Payment')
    reconcile_id = fields.Many2one('bank.reconcile', 'BR')
    batch_reconcile_id = fields.Many2one('bank.reconcile', 'Batch BR')
    
    