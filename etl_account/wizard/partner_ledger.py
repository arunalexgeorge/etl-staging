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
         
class PartnerLedger(models.TransientModel):
    _name = 'partner.ledger'
    _description = 'Partner Ledger' 
    
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    branch_id = fields.Many2one('res.branch', 'Branch')
    branch_ids = fields.Many2many('res.branch', string='Branches')
    partner_id = fields.Many2one('res.partner', 'Partner')
    company_id = fields.Many2one('res.company', 'Company', default=1)
    opening_balance = fields.Float('Opening Balance')
    closing_balance = fields.Float('Closing Balance')
    name = fields.Char('Description')
    line_ids = fields.One2many('partner.ledger.line', 'ledger_id', 'Lines')
    type = fields.Selection([
        ('ledger', 'Ledger Account'),
        ('monthly', 'Monthly Summary'),
        ('overdue', 'Overdue'),
        ], 'Report Type', default='ledger')
    
    def action_print(self):
        return self.env.ref('etl_account.action_report_legder').report_action(self)
    
    @api.model
    def default_get(self, def_fields):
        res = super(PartnerLedger, self).default_get(def_fields)
        res['branch_id'] = self.env.user.branch_id.id
        return res
    
    def get_opening_value_debit_due(self):
        dp = self.partner_id.invoice_decimal
        value = ''
        ob = self.opening_balance
        if ob > 0:
            value = formatLang(self.env, ob, digits=dp) + ' Dr'
        elif ob > 0:
            value = formatLang(self.env, -ob, digits=dp) + ' Cr'
        return value
    
    def get_opening_value_debit(self):
        dp = self.partner_id.invoice_decimal
        return self.opening_balance > 0 and formatLang(self.env, self.opening_balance, digits=dp) or ''
    
    def get_opening_value_credit(self):
        dp = self.partner_id.invoice_decimal
        return self.opening_balance < 0 and formatLang(self.env, -1*self.opening_balance, digits=dp) or ''
    
    def get_closing_value_debit(self):
        dp = self.partner_id.invoice_decimal
        return self.closing_balance > 0 and formatLang(self.env, self.closing_balance, digits=dp) or ''
    
    def get_closing_value_credit(self):
        dp = self.partner_id.invoice_decimal
        return self.closing_balance < 0 and formatLang(self.env, -1*self.closing_balance, digits=dp) or ''
    
    def get_total_opening(self):
        dp = self.partner_id.invoice_decimal
        ob = self.opening_balance
        for line in self.line_ids:
            ob += line.opening_amount
        value = ''
        if ob > 0:
            value = formatLang(self.env, ob, digits=dp) + ' Dr'
        elif ob > 0:
            value = formatLang(self.env, -ob, digits=dp) + ' Cr'
        return value
    
    def get_total_pending(self):
        dp = self.partner_id.invoice_decimal
        ob = self.opening_balance
        for line in self.line_ids:
            ob += line.pending_amount
        value = ''
        if ob > 0:
            value = formatLang(self.env, ob, digits=dp) + ' Dr'
        elif ob > 0:
            value = formatLang(self.env, -ob, digits=dp) + ' Cr'
        return value
    
    def get_opening_value_monthly(self):
        dp = self.partner_id.invoice_decimal
        ob = self.opening_balance
        value = ''
        if ob > 0:
            value = formatLang(self.env, ob, digits=dp) + ' Dr'
        elif ob > 0:
            value = formatLang(self.env, -ob, digits=dp) + ' Cr'
        return value
    
    def get_monthly_debit(self):
        dp = self.partner_id.invoice_decimal
        return formatLang(self.env, sum([line.debit for line in self.line_ids]), digits=dp)
    
    def get_monthly_credit(self):
        dp = self.partner_id.invoice_decimal
        return formatLang(self.env, sum([line.credit for line in self.line_ids]), digits=dp)
    
    def get_monthly_total(self):
        dp = self.partner_id.invoice_decimal
        total = self.opening_balance + sum([line.debit-line.credit for line in self.line_ids])
        return formatLang(self.env, total, digits=dp)
        
    @api.onchange('partner_id', 'start_date', 'end_date', 'branch_id', 'type')
    def onchange_partner(self):
        aml_obj = self.env['account.move.line']
        opening_balance, closing_balance = 0.0, 0.0
        lines = self.env['partner.ledger.line']
        if self.start_date and self.end_date and self.partner_id and self.type:
            partner_accounts = self.env['account.account'].search([('account_type', 'in', ('asset_receivable', 'liability_payable'))]).ids
            # if self.partner_id.property_account_receivable_id:
            #     partner_accounts.append(self.partner_id.property_account_receivable_id.id)
            # if self.partner_id.property_account_payable_id:
            #     partner_accounts.append(self.partner_id.property_account_payable_id.id)
            opening_domain = [
                ('account_id', 'in', partner_accounts),
                ('date', '<', self.start_date),
                ('move_id.state', '=', 'posted'),
                ('partner_id', '=', self.partner_id.id),
                ('branch_id', 'in', self.branch_ids.ids)
                ]
            tr_domain = [
                ('account_id', 'in', partner_accounts),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('move_id.state', '=', 'posted'),
                ('partner_id', '=', self.partner_id.id),
                ('branch_id', 'in', self.branch_ids.ids)
                ]
            if self.type == 'overdue':
                opening_domain.append(('amount_residual', '!=', 0))
                opening_amls = aml_obj.with_context(no_filter=True).search(opening_domain, order='date')
                opening_balance = round(sum([aml.amount_residual for aml in opening_amls]), 3)
                tr_domain.append(('amount_residual', '!=', 0))
                amls = aml_obj.with_context(no_filter=True).search(tr_domain, order='date')
            else:
                opening_amls = aml_obj.with_context(no_filter=True).search(opening_domain, order='date')
                opening_balance = round(sum([aml.debit - aml.credit for aml in opening_amls]), 3)
                amls = aml_obj.with_context(no_filter=True).search(tr_domain, order='date')
            closing_balance += opening_balance
            if self.type == 'ledger':
                for aml in amls:
                    lines += lines.new({
                        'move_line_id': aml.id,
                        'debit': aml.debit,
                        'credit': aml.credit,
                        'date': aml.date,
                        'voucher_no': aml.move_id.name,
                        'move_id': aml.move_id.id
                        })
                    closing_balance += aml.debit - aml.credit
            elif self.type == 'monthly':
                month_dic = {}
                for aml in amls:
                    month = aml.date.strftime('%m')
                    month_key = aml.date.strftime('%m-%Y')
                    if month_key in month_dic:
                        debit = month_dic[month_key]['debit'] + aml.debit
                        credit = month_dic[month_key]['credit'] + aml.credit
                        month_dic.update({
                            month_key: {
                                'debit': debit,
                                'credit': credit,
                                'month': month
                                }
                            })
                    else:
                        month_dic.update({
                            month_key: {
                                'debit': aml.debit,
                                'credit': aml.credit,
                                'month': month
                                }
                            })
                month_list = []
                for month_key in month_dic:
                    month_list.append({
                        'month_key': month_key,
                        'value': month_dic[month_key]
                        })
                month_list = sorted(month_list, key=lambda k: k['month_key'])
                for month in month_list:
                    debit = month['value']['debit']
                    credit = month['value']['credit']
                    closing_balance += debit - credit
                    lines += lines.new({
                        'debit': debit,
                        'credit': credit,
                        'month': month['value']['month'],
                        'closing_balance': closing_balance
                        })
            elif self.type == 'overdue':
                for aml in amls:
                    opening_amount = aml.debit - aml.credit
                    pending_amount = aml.amount_residual
                    due_date = aml.date_maturity or aml.date
                    due_days = (fields.Date.today() - due_date).days
                    if due_days < 0:
                        due_days = 0
                    lines += lines.new({
                        'opening_amount': opening_amount,
                        'pending_amount': pending_amount,
                        'date': aml.date,
                        'due_date': due_date,
                        'voucher_no': aml.move_id.name,
                        'due_days': due_days,
                        'move_id': aml.move_id.id
                        })
                    closing_balance += pending_amount
        closing_balance = round(closing_balance, 3)
        self.opening_balance = opening_balance
        self.closing_balance = closing_balance
        self.name = 'Partner Ledger'
        self.line_ids = lines
    
class PartnerLedgerLine(models.TransientModel):
    _name = 'partner.ledger.line'
    _description = 'Partner Ledger Line'
    
    @api.depends('move_line_id', 'ledger_id.start_date', 'ledger_id.end_date', 'ledger_id.partner_id')
    def _compute_aml_details(self):
        for line in self:
            if line.move_line_id:
                ml = line.move_line_id
                move = ml.move_id
                voucher_type = 'jv'
                if move.payment_id:
                    payment = move.payment_id
                    if payment.is_internal_transfer:
                        voucher_type = 'contra'
                    elif payment.payment_type == 'inbound':
                        voucher_type = 'receipt'
                    elif payment.payment_type == 'outbound':
                        voucher_type = 'payment'
                else:
                    if move.move_type == 'out_invoice':
                        voucher_type = 'ci'
                    elif move.move_type == 'out_refund':
                        voucher_type = 'cn'
                    elif move.move_type == 'in_invoice':
                        voucher_type = 'pi'
                    if move.move_type == 'in_refund':
                        voucher_type = 'dn'
                name = ml.account_id.name
                line.name = name
                line.voucher_type = voucher_type
    
    def get_formatted_value(self, amount):
        dp = self.ledger_id.partner_id.invoice_decimal
        return amount and formatLang(self.env, amount, digits=dp) or ''
    
    def get_due_formatted_value(self, amount):
        dp = self.ledger_id.partner_id.invoice_decimal
        if amount > 0:
            value =  formatLang(self.env, amount, digits=dp)+' Dr'
        elif amount < 0:
            value =  formatLang(self.env, -amount, digits=dp)+' Cr'
        return value
    
    def get_due_days(self):
        return self.due_days > 0 and self.due_days or '' 
    
    date = fields.Date('Date')
    debit = fields.Float('Debit')
    credit = fields.Float('Credit')
    opening_amount = fields.Float('Opening Amount')
    pending_amount = fields.Float('Pending Amount')
    closing_balance = fields.Float('Closing Balance')
    due_date = fields.Date('Due Date')
    due_days = fields.Integer('Due Days')
    name = fields.Char('Particulars', compute='_compute_aml_details', store=True)
    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ('contra', 'Contra'),
        ('jv', 'JV'),
        ('ci', 'Invoice'),
        ('cn', 'Credit Note'),
        ('pi', 'Purchase Bill'),
        ('dn', 'Debit Note')
        ], 'Voucher Type', compute='_compute_aml_details', store=True)
    voucher_no = fields.Char('Voucher #')
    move_id = fields.Many2one('account.move', 'Voucher No.')
    move_line_id = fields.Many2one('account.move.line', 'AML')
    ledger_id = fields.Many2one('partner.ledger', 'PL')
    month = fields.Selection([
        ('01', 'January'),
        ('02', 'February'),
        ('03', 'March'),
        ('04', 'April'),
        ('05', 'May'),
        ('06', 'June'),
        ('07', 'July'),
        ('08', 'August'),
        ('09', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
        ], 'Month')
    
    