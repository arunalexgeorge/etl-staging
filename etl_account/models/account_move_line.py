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
from datetime import timedelta
import string
from odoo.tools import (
    date_utils,
    email_re,
    email_split,
    float_compare,
    float_is_zero,
    float_repr,
    format_amount,
    format_date,
    formatLang,
    frozendict,
    get_lang,
    is_html_empty,
    sql
)
from datetime import datetime
import requests
import json
from odoo.tools.misc import formatLang

class SequenceMixin(models.AbstractModel):
    _inherit = 'sequence.mixin'

    @api.constrains(lambda self: (self._sequence_field, self._sequence_date_field))
    def _constrains_date_sequence(self):
        constraint_date = fields.Date.to_date(self.env['ir.config_parameter'].sudo().get_param(
            'sequence.mixin.constraint_start_date',
            '1970-01-01'
        ))
        for record in self:
            continue

class AccountMoveReversal(models.TransientModel):
    """
    Account move reversal wizard, it cancel an account move by reversing it.
    """
    _inherit = 'account.move.reversal'
    
    @api.depends('move_type')
    def _compute_journal_id(self):
        for record in self:
            if record.move_type == 'out_invoice':
                record.journal_id = self.env.company.cn_journal_id
            elif record.move_type == 'in_invoice':
                record.journal_id = self.env.company.dn_journal_id
                
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Use Specific Journal',
        required=True,
        compute='_compute_journal_id',
        readonly=False,
        store=True,
        check_company=True,
        help='If empty, uses the journal of the journal entry to be reversed.',
        )

class BankRecWidget(models.Model):
    _inherit = "bank.rec.widget"
    
    @api.depends('st_line_id')
    def _compute_amls_widget(self):
        for wizard in self:
            st_line = wizard.st_line_id

            context = {
                'search_view_ref': 'account_accountant.view_account_move_line_search_bank_rec_widget',
                'tree_view_ref': 'account_accountant.view_account_move_line_list_bank_rec_widget',
                }

            if wizard.partner_id:
                context['search_default_partner_id'] = wizard.partner_id.id

            dynamic_filters = []

            # == Dynamic Customer/Vendor filter ==
            journal = st_line.journal_id

            account_ids = set()

            inbound_accounts = journal._get_journal_inbound_outstanding_payment_accounts() - journal.default_account_id
            outbound_accounts = journal._get_journal_outbound_outstanding_payment_accounts() - journal.default_account_id

            # Matching on debit account.
            for account in inbound_accounts:
                account_ids.add(account.id)

            # Matching on credit account.
            for account in outbound_accounts:
                account_ids.add(account.id)
            if st_line.amount > 0.0:
                dynamic_filters.append({
                    'name': 'receivable_matching',
                    'description': st_line.amount,
                    'domain': [
                        ('account_id', 'in', tuple(account_ids)),
                        ('amount_residual', '=', st_line.amount)
                        ],
                    'no_separator': True,
                    'is_default': st_line.amount > 0.0,
                    })
            elif st_line.amount < 0.0:
                dynamic_filters.append({
                'name': 'payable_matching',
                'description': st_line.amount,
                'domain': [
                    ('account_id', 'in', tuple(account_ids)),
                    ('amount_residual', '=', st_line.amount)
                    ],
                'is_default': st_line.amount < 0.0,
                })

            for dynamic_filter in dynamic_filters:
                dynamic_filter['domain'] = str(dynamic_filter['domain'])
            wizard.amls_widget = {
                'domain': st_line._get_default_amls_matching_domain(),
                'dynamic_filters': dynamic_filters,
                'context': context,
                }
            
    amls_widget = fields.Binary(
        compute='_compute_amls_widget',
        readonly=False,)
    
class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"
    
    @api.depends('move_id', 'move_id.branch_id', 'move_id.state')
    def _compute_branch(self):
        for line in self:
            line.branch_id = line.move_id and line.move_id.branch_id.id or False 
        
    branch_id = fields.Many2one('res.branch', "Branch", compute='_compute_branch', store=True)
    
    def _get_default_amls_matching_domain(self):
        journal = self.journal_id
        account_ids = set()
        inbound_accounts = journal._get_journal_inbound_outstanding_payment_accounts() - journal.default_account_id
        outbound_accounts = journal._get_journal_outbound_outstanding_payment_accounts() - journal.default_account_id

        for account in inbound_accounts:
            account_ids.add(account.id)

        for account in outbound_accounts:
            account_ids.add(account.id)

        return [
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('reconciled', '=', False),
            ('account_id.reconcile', '=', True),
            ('account_id', 'in', list(account_ids)),
            ('statement_line_id', '!=', self.id),
            ]
          
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    def delete_jv(self):
        for aml in self:
            self._cr.execute('delete from account_move where id=%s'% (aml.move_id.id))
        return True
    
    def action_correct_tax_entries(self):
        move_ids = []
        for line in self:
            move_ids.append(line.move_id.id)
        move_ids = list(set(move_ids))
        for move in self.env['account.move'].browse(move_ids):
            move.action_correct_tax_entries()
            # move.action_correct_tax_entries2()
        return True
    
    def _create_in_invoice_svl(self):
        return self.env['stock.valuation.layer'].sudo()
    
    def get_formatted_amount(self, amount, dp):
        return formatLang(self.env, amount, digits=dp, currency_obj=self.move_id.currency_id)
    
    def get_formatted_value(self, amount):
        return amount and formatLang(self.env, amount) or ''

    def correct_moveline_data(self):
        if self.account_id.id == 5649:
            mtv_obj = self.env['mail.tracking.value']
            mtvs = mtv_obj.search([
                ('new_value_integer', '=', 5649),
                ('mail_message_id.res_id', '=', self.move_id.id)
                ])
            old_account_id = mtvs[0].old_value_integer
            old_acc_code = self.env['account.account'].browse(old_account_id).code
            acc_emp_dic = {'105004001': 'EM0005', '105004065': 'EM0006', '105004003': 'EM0013', '105004004': 'EM0015', '105004070': 'EM0016', '105004071': 'EM0018', '105004005': 'EM0020', '105004007': 'EM0022', '105004008': 'EM0023', '105004010': 'EM0025', '105004073': 'EM0027', '105004011': 'EM0029', '105004066': 'EM0031', '105004013': 'EM0033', '105004074': 'EM0035', '105004068': 'EM0036', '105004014': 'EM0037', '105004016': 'EM0041', '105004019': 'EM0044', '105004021': 'EM0046', '105004022': 'EM0047', '105004023': 'EM0048', '105004025': 'EM0050', '105004027': 'EM0053', '105004028': 'EM0054', '105004031': 'EM0056', '105004032': 'EM0062', '105004082': 'EM0063', '105004084': 'EM0064', '105004067': 'EM0071', '105004034': 'EM0072', '105004035': 'EM0074', '105004036': 'EM0076', '105004083': 'EM0078', '105004037': 'EM0079', '105004038': 'EM0080', '105004039': 'EM0081', '105004040': 'EM0082', '105004042': 'EM0085', '105004043': 'EM0086', '105004044': 'EM0087', '105004045': 'EM0088', '105004069': 'EM0089', '105004072': 'EM0091', '105004047': 'EM0092', '105004048': 'EM0094', '105004049': 'EM0095', '105004050': 'EM0096', '105004051': 'EM0097', '105004053': 'EM0098', '105004054': 'EM0099', '105004055': 'EM0100', '105004056': 'EM0103', '105004058': 'EM0106', '105004059': 'EM0107', '105004046': 'EM0109', '105004062': 'EM0110', '105004063': 'EM0111', '105004030': 'EM0112'}
            if old_acc_code in acc_emp_dic:
                partner = self.env['res.partner'].search([('partner_code', '=', acc_emp_dic[old_acc_code])])
                if partner:
                    self.partner_id = partner.id
        return True
    
    def _get_lock_date_protected_fields(self):
        """ Returns the names of the fields that should be protected by the accounting fiscal year and tax lock dates
        """
        tax_fnames = []#['balance', 'tax_line_id', 'tax_ids', 'tax_tag_ids']
        fiscal_fnames = []#tax_fnames + ['account_id', 'journal_id', 'amount_currency', 'currency_id', 'partner_id']
        reconciliation_fnames = []#['account_id', 'date', 'balance', 'amount_currency', 'currency_id', 'partner_id']
        return {
            'tax': tax_fnames,
            'fiscal': fiscal_fnames,
            'reconciliation': reconciliation_fnames,
            }
    
    @api.constrains('account_id', 'display_type')
    def _check_payable_receivable(self):
        for line in self:
            account_type = line.account_id.account_type
            # if line.move_id.is_sale_document(include_receipts=True):
            #     if (line.display_type == 'payment_term') ^ (account_type == 'asset_receivable'):
            #         raise UserError(_("Any journal item on a receivable account must have a due date and vice versa."))
            # if line.move_id.is_purchase_document(include_receipts=True):
            #     if (line.display_type == 'payment_term') ^ (account_type == 'liability_payable'):
            #         raise UserError(_("Any journal item on a payable account must have a due date and vice versa."))
                
    @api.depends('tax_ids', 'currency_id', 'partner_id', 'analytic_distribution', 
        'balance', 'partner_id', 'move_id.partner_id', 'price_unit', 
        'discount_value', 'discount', 'move_id.state')
    def _compute_all_tax_new(self):
        for line in self:
            dp_dic = {2: 0.01, 3: 0.001}
            invoice_decimal = line.move_id and line.move_id.partner_id and line.move_id and line.move_id.partner_id.invoice_decimal or False
            if not invoice_decimal:
                invoice_decimal = 2
            dp = dp_dic[invoice_decimal]
            sign = line.move_id.direction_sign
            if line.display_type == 'tax':
                line.compute_all_tax = {}
                line.compute_all_tax_dirty = False
                continue
            if line.display_type == 'product' and line.move_id.is_invoice(True):
                price_unit = line.price_unit * (1 - 0.01 * line.discount)
                price_unit = round(tools.float_round(price_unit, precision_rounding=dp), invoice_decimal)
                price_unit_disc = price_unit - line.discount_value
                price_unit = round(tools.float_round(price_unit_disc, precision_rounding=dp), invoice_decimal)
                amount_currency = sign * price_unit
                handle_price_include = True
                quantity = line.quantity
            else:
                amount_currency = line.amount_currency
                handle_price_include = False
                quantity = 1
            amount_currency = round(tools.float_round(amount_currency, precision_rounding=dp), invoice_decimal)
            compute_all_currency = line.tax_ids.compute_all(
                amount_currency,
                currency=line.currency_id,
                quantity=quantity,
                product=line.product_id,
                partner=line.move_id.partner_id or line.partner_id,
                is_refund=line.is_refund,
                handle_price_include=handle_price_include,
                include_caba_tags=line.move_id.always_tax_exigible,
                fixed_multiplicator=sign,
                )
            rate = line.amount_currency / line.balance if line.balance else 1
            line.compute_all_tax_dirty = True
            line.compute_all_tax = {
                frozendict({
                    'tax_repartition_line_id': tax['tax_repartition_line_id'],
                    'group_tax_id': tax['group'] and tax['group'].id or False,
                    'account_id': tax['account_id'] or line.account_id.id,
                    'currency_id': line.currency_id.id,
                    'analytic_distribution': (tax['analytic'] or not tax['use_in_tax_closing']) and line.analytic_distribution,
                    'tax_ids': [(6, 0, tax['tax_ids'])],
                    'tax_tag_ids': [(6, 0, tax['tag_ids'])],
                    'partner_id': line.move_id.partner_id.id or line.partner_id.id,
                    'move_id': line.move_id.id,
                }): {
                    'name': tax['name'],
                    'balance': tax['amount'] / rate,
                    'amount_currency': tax['amount'],
                    'tax_base_amount': tax['base'] / rate * (-1 if line.tax_tag_invert else 1),
                    }
                for tax in compute_all_currency['taxes'] if tax['amount']
                }
            if not line.tax_repartition_line_id:
                line.compute_all_tax[frozendict({'id': line.id})] = {
                    'tax_tag_ids': [(6, 0, compute_all_currency['base_tags'])],
                    }
                
    @api.depends('move_id.payment_reference','move_id.state','move_id.invoice_date', 'quantity', 
        'discount', 'price_unit', 'tax_ids', 'currency_id', 'discount_value', 'tax_tag_ids')
    def _compute_totals(self):
        dp_dic = {2: 0.01, 3: 0.001}
        for line in self:
            invoice_decimal = line.move_id and line.move_id.partner_id and line.move_id.partner_id.invoice_decimal or False
            if not invoice_decimal:
                invoice_decimal = 2
            dp = dp_dic[invoice_decimal]
            if line.display_type != 'product':
                line.price_total = line.price_subtotal = False
            # Compute 'price_subtotal'.
            
            price_unit = line.price_unit * (1 - 0.01 * line.discount)
            price_unit = round(tools.float_round(price_unit, precision_rounding=dp), invoice_decimal)
            price_unit_disc = price_unit - line.discount_value
            line_discount_price_unit = round(tools.float_round(price_unit_disc, precision_rounding=dp), invoice_decimal)
        
            subtotal = line.quantity * line_discount_price_unit
            
            subtotal = round(tools.float_round(subtotal, precision_rounding=dp), invoice_decimal)
            # Compute 'price_total'.
            tax_base_amount = 0
            if line.tax_ids:
                taxes_res = line.tax_ids.compute_all(
                    line_discount_price_unit,
                    quantity=line.quantity,
                    currency=line.currency_id,
                    product=line.product_id,
                    partner=line.partner_id,
                    is_refund=line.is_refund,
                    )
                total_excluded_rounded = round(tools.float_round(taxes_res['total_excluded'], precision_rounding=dp), invoice_decimal)
                total_included_rounded = round(tools.float_round(taxes_res['total_included'], precision_rounding=dp), invoice_decimal)
                line.price_subtotal = total_excluded_rounded
                line.price_total = total_included_rounded
            else:
                line.price_total = subtotal
                line.price_subtotal = subtotal
            tax_base_amount = 0.0
            if line.tax_line_id:
                if line.move_id.is_invoice(include_receipts=True):
                    tax_totals = line.move_id.tax_totals
                    if tax_totals and 'groups_by_subtotal' in tax_totals and 'Untaxed Amount' in tax_totals['groups_by_subtotal']:
                        for tax_line in tax_totals['groups_by_subtotal']['Untaxed Amount']:
                            if line.tax_line_id.tax_group_id.name == tax_line['tax_group_name']:
                                tax_base_amount += tax_line['tax_group_base_amount']
                else:
                    amount = line.debit + line.credit
                    tax_base_amount += abs(amount * 100 / line.tax_line_id.amount)
            line.tax_base_amount = tax_base_amount
                
    def _convert_to_tax_base_line_dict(self):
        self.ensure_one()
        dp_dic = {2: 0.01, 3: 0.001}
        invoice_decimal = self.move_id and self.move_id.partner_id and self.move_id.partner_id.invoice_decimal or False
        if not invoice_decimal:
            invoice_decimal = 2
        dp = dp_dic[invoice_decimal]
        is_invoice = self.move_id.is_invoice(include_receipts=True)
        sign = -1 if self.move_id.is_inbound(include_receipts=True) else 1
        price_unit = self.price_unit * (1 - 0.01 * self.discount)
        price_unit = round(tools.float_round(price_unit, precision_rounding=dp), invoice_decimal)
        price_unit_disc = price_unit - self.discount_value
        price_unit = round(tools.float_round(price_unit_disc, precision_rounding=dp), invoice_decimal)
        quantity = self.quantity if is_invoice else 1.0
        price_subtotal = price_unit * quantity
        price_subtotal = round(tools.float_round(price_subtotal, precision_rounding=dp), invoice_decimal)
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.partner_id,
            currency=self.currency_id,
            product=self.product_id,
            taxes=self.tax_ids,
            price_unit=price_unit if is_invoice else self.amount_currency,
            quantity=quantity,
            discount=0.0,
            account=self.account_id,
            analytic_distribution=self.analytic_distribution,
            price_subtotal=sign * self.amount_currency,
            is_refund=self.is_refund,
            rate=(abs(self.amount_currency) / abs(self.balance)) if self.balance else 1.0)
        
    price_subtotal = fields.Monetary('Subtotal', compute='_compute_totals', store=True, currency_field='currency_id')
    price_total = fields.Monetary('Total', compute='_compute_totals', store=True, currency_field='currency_id')
    discount = fields.Float('Discount (%)', digits='Discount', default=0.0)
    discount_value = fields.Float('Discount/KG', digits='Discount', default=0.0)
    compute_all_tax = fields.Binary(compute='_compute_all_tax_new')
    compute_all_tax_dirty = fields.Boolean(compute='_compute_all_tax_new')
    tax_ids = fields.Many2many(
        comodel_name='account.tax',
        string="Taxes",
        compute='_compute_tax_ids', store=True, readonly=False, precompute=True,
        context={'active_test': False},
        check_company=True)
    sl_no = fields.Integer("SL No.", compute='_compute_sl_no', store=True)
    tax_base_amount = fields.Float('Tax Base Amount', compute='_compute_totals', store=True)
    bank_date = fields.Date('Bank Date', copy=False)
    inst_no = fields.Char('Instrument #')
    inst_date = fields.Date('Instrument Date')
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account',
        compute='_compute_account_id', store=True, readonly=False, precompute=True,
        inverse='_inverse_account_id',
        index=True,
        auto_join=True,
        ondelete="cascade",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id), ('is_off_balance', '=', False)]",
        check_company=True,
        tracking=True,
        )
    
    @api.depends('display_type', 'company_id', 'move_id.dn_type', 'move_id.cn_type')
    def _compute_account_id(self):
        term_lines = self.filtered(lambda line: line.display_type == 'payment_term')
        if term_lines:
            for line in term_lines:
                if line.move_id.is_customer_doc():
                    account_id = line.move_id.partner_id.property_account_receivable_id.id
                else:
                    account_id = line.move_id.partner_id.property_account_payable_id.id
                if line.move_id.fiscal_position_id:
                    account_id = self.move_id.fiscal_position_id.map_account(self.env['account.account'].browse(account_id))
                line.account_id = account_id

        product_lines = self.filtered(lambda line: line.display_type == 'product' and line.move_id.is_invoice(True))
        for line in product_lines:
            if line.product_id:
                fiscal_position = line.move_id.fiscal_position_id
                accounts = line.with_company(line.company_id).product_id.product_tmpl_id.get_product_accounts(fiscal_pos=fiscal_position)
                if line.move_id.is_customer_doc:
                    line.account_id = accounts['income'] or line.account_id
                elif line.move_id.is_vendor_doc:
                    line.account_id = accounts['expense'] or line.account_id
            elif line.partner_id:
                line.account_id = self.env['account.account']._get_most_frequent_account_for_partner(
                    company_id=line.company_id.id,
                    partner_id=line.partner_id.id,
                    move_type=line.move_id.move_type,
                    )
        for line in self:
            if not line.account_id and line.display_type not in ('line_section', 'line_note'):
                previous_two_accounts = line.move_id.line_ids.filtered(
                    lambda l: l.account_id and l.display_type == line.display_type
                )[-2:].account_id
                if len(previous_two_accounts) == 1:
                    line.account_id = previous_two_accounts
                else:
                    line.account_id = line.move_id.journal_id.default_account_id
    
    @api.depends('sequence')
    def _compute_sl_no(self):
        for line in self:
            line.sl_no = line.sequence
            
    def _get_computed_taxes(self):
        self.ensure_one()
        print('1'*100)
        print(self.move_id.is_customer_doc())
        print('2'*100)
        if self.move_id.is_customer_doc():
            # Out invoice.
            if self.product_id.taxes_id:
                tax_ids = self.product_id.taxes_id.filtered(lambda tax: tax.company_id == self.move_id.company_id)
                if self.move_id.partner_id and self.move_id.partner_id.tcs_ok:
                    taxes_ids = tax_ids and tax_ids.ids
                    taxes_ids.append(self.move_id.company_id.tcs_tax_id.id)
                    tax_ids = self.env['account.tax'].browse(taxes_ids)
            elif self.account_id.tax_ids:
                tax_ids = self.account_id.tax_ids
            else:
                tax_ids = self.env['account.tax']
            if not tax_ids and self.display_type == 'product':
                tax_ids = self.move_id.company_id.account_sale_tax_id
        elif self.move_id.is_vendor_doc():
            # In invoice.
            if self.product_id.supplier_taxes_id:
                tax_ids = self.product_id.supplier_taxes_id.filtered(lambda tax: tax.company_id == self.move_id.company_id)
            elif self.account_id.tax_ids:
                tax_ids = self.account_id.tax_ids
            else:
                tax_ids = self.env['account.tax']
            if not tax_ids and self.display_type == 'product':
                tax_ids = self.move_id.company_id.account_purchase_tax_id
        else:
            # Miscellaneous operation.
            tax_ids = self.account_id.tax_ids

        if self.company_id and tax_ids:
            tax_ids = tax_ids.filtered(lambda tax: tax.company_id == self.company_id)

        if tax_ids and self.move_id.fiscal_position_id:
            tax_ids = self.move_id.fiscal_position_id.map_tax(tax_ids)

        return tax_ids
    
    @api.depends('product_id', 'product_uom_id', 'move_id.payment_reference')
    def _compute_tax_ids(self):
        for line in self:
            if line.display_type in ('line_section', 'line_note'):
                continue
            if line.product_id or line.account_id.tax_ids or not line.tax_ids:
                line.tax_ids = line._get_computed_taxes()
    
    @api.onchange('partner_id')
    def _inverse_partner_id(self):
        self._conditional_add_to_compute('account_id', lambda line: (
            line.display_type == 'payment_term'  # recompute based on settings
            or (line.move_id.is_invoice(True) and line.display_type == 'product' and not line.product_id)  # recompute based on most used account
            ))
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id and self.move_id.move_type == 'entry':
            if self.display_type == 'product':
                account_id = self.account_id
                if self.partner_id.partner_type in ('customer', 'customer_exp'):
                    account_id = self.partner_id.property_account_receivable_id and self.partner_id.property_account_receivable_id.id or False
                elif self.partner_id.partner_type in ('vendor', 'vendor_for', 'employee'):
                    account_id = self.partner_id.property_account_payable_id and self.partner_id.property_account_payable_id.id or False
                self.account_id = account_id
        