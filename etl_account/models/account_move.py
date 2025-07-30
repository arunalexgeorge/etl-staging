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
import qrcode
import base64
from io import BytesIO
import logging
logger = logging.getLogger(__name__)
from collections import defaultdict
from odoo.tools.float_utils import float_round
from textwrap import shorten
from bisect import bisect_left
from collections import defaultdict

class Account(models.Model):
    _inherit = "account.account"
    
    active = fields.Boolean(default=True)
    account_type = fields.Selection(
        selection=[
            ("asset_receivable", "Receivable"),
            ("asset_cash", "Bank and Cash"),
            ("asset_current", "Current Assets"),
            ("asset_non_current", "Non-current Assets"),
            ("asset_prepayments", "Prepayments"),
            ("asset_fixed", "Fixed Assets"),
            ("liability_payable", "Payable"),
            ("liability_credit_card", "Credit Card"),
            ("liability_current", "Current Liabilities"),
            ("liability_non_current", "Non-current Liabilities"),
            ("equity", "Equity"),
            ("equity_unaffected", "Current Year Earnings"),
            ("income", "Income"),
            ("income_other", "Other Income"),
            ("expense_purchase", "Purchases"),
            ("expense_direct_cost", "Direct Expenses"),
            ("expense", "Indirect Expenses"),
            ("expense_depreciation", "Depreciation"),
            ("off_balance", "Off-Balance Sheet"),
        ],
        string="Type", tracking=True,
        required=True,
        compute='_compute_account_type', store=True, readonly=False, precompute=True)
    
    @api.depends('code')
    def _compute_account_type(self):
        accounts_to_process = self.filtered(lambda r: r.code and not r.account_type)
        all_accounts = self.search_read(
            domain=[('company_id', 'in', accounts_to_process.company_id.ids)],
            fields=['code', 'account_type', 'company_id'],
            order='code')
        print('all_accounts:',all_accounts)
        accounts_with_codes = defaultdict(dict)
        for account in all_accounts:
            accounts_with_codes[account['company_id'][0]][account['code']] = account['account_type']
        print('accounts_with_codes:',accounts_with_codes)
        for account in accounts_to_process:
            codes_list = list(accounts_with_codes[account.company_id.id].keys())
            print('codes_list:',codes_list)
            closest_index = bisect_left(codes_list, account.code) - 1
            print('closest_index:',closest_index)
            account_type = accounts_with_codes[account.company_id.id][codes_list[closest_index]] if closest_index != -1 else 'asset_current'
            print('account_type:',account_type)
            account.account_type = account_type 
            
class AccountJournal(models.Model):
    _inherit = "account.journal"

    code = fields.Char('Short Code', size=6, required=True)
    payment_voucher = fields.Boolean('Payment Voucher')
    
    def correct_reconcile(self):
        sls = self.env['account.bank.statement.line'].with_context(no_filter=True).search([('journal_id', '=', self.id)])
        accounts = self._get_journal_inbound_outstanding_payment_accounts() \
            + self._get_journal_outbound_outstanding_payment_accounts()
        account_ids = [account.id for account in accounts]
        for sl in sls:
            for line in sl.move_id.line_ids:
                for md in line.matched_debit_ids:
                    self._cr.execute("""update account_move_line set bank_date='%s' where id=%s"""% (sl.date, md.debit_move_id.id))
                    self._cr.execute("""update account_move set bank_date='%s' where id=%s"""% (sl.date, md.debit_move_id.move_id.id))
                    self._cr.execute("""update account_move_line set bank_date='%s' where id=%s"""% (sl.date, md.credit_move_id.id))
                    self._cr.execute("""update account_move set bank_date='%s' where id=%s"""% (sl.date, md.credit_move_id.move_id.id))
                    self._cr.execute('delete from account_partial_reconcile where debit_move_id=%s'% (md.debit_move_id.id))
                    self._cr.execute('delete from account_partial_reconcile where credit_move_id=%s'% (md.credit_move_id.id))
                for md in line.matched_credit_ids:
                    self._cr.execute("""update account_move_line set bank_date='%s' where id=%s"""% (sl.date, md.debit_move_id.id))
                    self._cr.execute("""update account_move set bank_date='%s' where id=%s"""% (sl.date, md.debit_move_id.move_id.id))
                    self._cr.execute("""update account_move_line set bank_date='%s' where id=%s"""% (sl.date, md.credit_move_id.id))
                    self._cr.execute("""update account_move set bank_date='%s' where id=%s"""% (sl.date, md.credit_move_id.move_id.id))
                    self._cr.execute('delete from account_partial_reconcile where debit_move_id=%s'% (md.debit_move_id.id))
                    self._cr.execute('delete from account_partial_reconcile where credit_move_id=%s'% (md.credit_move_id.id))
            
            self._cr.execute('delete from account_move where id=%s'% (sl.move_id.id))
            self._cr.execute('delete from account_bank_statement_line where id=%s'% (sl.id))
        self._cr.execute("""update account_move_line set account_id=%s where account_id in %s"""% (self.default_account_id.id, tuple(account_ids)))
        return True
    
    def get_journal_dashboard_datas(self):
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        currency = self.currency_id or self.company_id.currency_id
        number_to_reconcile = number_to_check = last_balance = 0
        has_at_least_one_statement = False
        bank_account_balance = nb_lines_bank_account_balance = 0
        outstanding_pay_account_balance = nb_lines_outstanding_pay_account_balance = 0
        title = ''
        number_draft = number_waiting = number_late = to_check_balance = 0
        sum_draft = sum_waiting = sum_late = 0.0
        if self.type in ('bank', 'cash'):
            # last_statement = self._get_last_bank_statement(
            #     domain=[('move_id.state', '=', 'posted')])
            # last_balance = last_statement.balance_end
            # has_at_least_one_statement = bool(last_statement)
            bank_account_balance, nb_lines_bank_account_balance = self._get_journal_bank_account_balance(
                domain=[('parent_state', '=', 'posted')])
            outstanding_pay_account_balance, nb_lines_outstanding_pay_account_balance = self._get_journal_outstanding_payments_account_balance(
                domain=[('parent_state', '=', 'posted')])
            
            aml_obj = self.env['account.move.line']
            amls = aml_obj.with_context(no_filter=True).search([
                ('account_id', '=', self.default_account_id.id),
                ('bank_date', '=', False),
                ('move_id.state', '=', 'posted')
                ], order='date')
            unrec_total = 0
            for aml in amls:
                if aml.payment_id:
                    if not aml.payment_id.batch_payment_id:
                        number_to_reconcile += 1
                        unrec_total += aml.credit - aml.debit
            
            batch_payments = self.env['account.batch.payment'].with_context(no_filter=True).search([
                ('journal_id', '=', self.id),
                ('bank_date', '=', False),
                ('state', '!=', 'draft')
                ], order='date')
            
            for batch_payment in batch_payments:
                number_to_reconcile += 1
                unrec_total -= batch_payment.amount
            
            if number_to_reconcile > 0:
                has_at_least_one_statement = True
            last_balance = round(bank_account_balance, 3) + round(unrec_total, 3)
            if self.default_account_id:
                query = '''
                    SELECT COUNT(st_line.id)
                    FROM account_bank_statement_line st_line
                    JOIN account_move st_line_move ON st_line_move.id = st_line.move_id
                    JOIN account_move_line aml ON aml.move_id = st_line_move.id
                    WHERE st_line_move.journal_id IN %s
                    AND NOT st_line.is_reconciled
                    AND st_line_move.to_check IS NOT TRUE
                    AND st_line_move.state = 'posted'
                    AND aml.account_id = %s
                    AND st_line.branch_id IN %s
                '''
                self._cr.execute(query, [tuple(self.ids), self.default_account_id.id, tuple(branch_ids)])
                number_to_reconcile = self.env.cr.fetchone()[0]
            else:
                number_to_reconcile = 0

            to_check_ids = self.to_check_ids()
            number_to_check = len(to_check_ids)
            to_check_balance = sum([r.amount for r in to_check_ids])
        #TODO need to check if all invoices are in the same currency than the journal!!!!
        elif self.type in ['sale', 'purchase']:
            title = _('Bills to pay') if self.type == 'purchase' else _('Invoices owed to you')
            self.env['account.move'].flush_model()

            (query, query_args) = self._get_open_bills_to_pay_query()
            self.env.cr.execute(query, query_args)
            query_results_to_pay = self.env.cr.dictfetchall()

            (query, query_args) = self._get_draft_bills_query()
            self.env.cr.execute(query, query_args)
            query_results_drafts = self.env.cr.dictfetchall()

            (query, query_args) = self._get_late_bills_query()
            self.env.cr.execute(query, query_args)
            late_query_results = self.env.cr.dictfetchall()

            curr_cache = {}
            (number_waiting, sum_waiting) = self._count_results_and_sum_amounts(query_results_to_pay, currency, curr_cache=curr_cache)
            (number_draft, sum_draft) = self._count_results_and_sum_amounts(query_results_drafts, currency, curr_cache=curr_cache)
            (number_late, sum_late) = self._count_results_and_sum_amounts(late_query_results, currency, curr_cache=curr_cache)
            read = self.env['account.move'].read_group([('journal_id', '=', self.id), ('to_check', '=', True)], ['amount_total_signed'], 'journal_id', lazy=False)
            if read:
                number_to_check = read[0]['__count']
                to_check_balance = read[0]['amount_total_signed']
        elif self.type == 'general':
            read = self.env['account.move'].read_group([('journal_id', '=', self.id), ('to_check', '=', True)], ['amount_total_signed'], 'journal_id', lazy=False)
            if read:
                number_to_check = read[0]['__count']
                to_check_balance = read[0]['amount_total_signed']

        is_sample_data = self.kanban_dashboard_graph and any(data.get('is_sample_data', False) for data in json.loads(self.kanban_dashboard_graph))

        return {
            'number_to_check': number_to_check,
            'to_check_balance': formatLang(self.env, to_check_balance, currency_obj=currency),
            'number_to_reconcile': number_to_reconcile,
            'account_balance': formatLang(self.env, currency.round(bank_account_balance), currency_obj=currency),
            'has_at_least_one_statement': has_at_least_one_statement,
            'nb_lines_bank_account_balance': nb_lines_bank_account_balance,
            'outstanding_pay_account_balance': formatLang(self.env, currency.round(outstanding_pay_account_balance), currency_obj=currency),
            'nb_lines_outstanding_pay_account_balance': nb_lines_outstanding_pay_account_balance,
            'last_balance': formatLang(self.env, currency.round(last_balance) + 0.0, currency_obj=currency),
            'number_draft': number_draft,
            'number_waiting': number_waiting,
            'number_late': number_late,
            'sum_draft': formatLang(self.env, currency.round(sum_draft) + 0.0, currency_obj=currency),
            'sum_waiting': formatLang(self.env, currency.round(sum_waiting) + 0.0, currency_obj=currency),
            'sum_late': formatLang(self.env, currency.round(sum_late) + 0.0, currency_obj=currency),
            'currency_id': currency.id,
            'bank_statements_source': self.bank_statements_source,
            'title': title,
            'is_sample_data': is_sample_data,
            'company_count': len(self.env.companies)
            }
        
    
    def _get_journal_outstanding_payments_account_balance(self, domain=None, date=None):
        self.ensure_one()
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        self.env['account.move.line'].check_access_rights('read')
        conversion_date = date or fields.Date.context_today(self)

        accounts = self._get_journal_inbound_outstanding_payment_accounts().union(self._get_journal_outbound_outstanding_payment_accounts())
        if not accounts:
            return 0.0, 0

        # Allow user managing payments without any statement lines.
        # In that case, the user manages transactions only using the register payment wizard.
        if self.default_account_id in accounts:
            return 0.0, 0

        domain = (domain or []) + [
            ('account_id', 'in', tuple(accounts.ids)),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('parent_state', '!=', 'cancel'),
            ('reconciled', '=', False),
            ('journal_id', '=', self.id),
            ('branch_id', 'in', branch_ids)
            ]
        query = self.env['account.move.line']._where_calc(domain)
        tables, where_clause, where_params = query.get_sql()

        self._cr.execute('''
            SELECT
                COUNT(account_move_line.id) AS nb_lines,
                account_move_line.currency_id,
                account.reconcile AS is_account_reconcile,
                SUM(account_move_line.amount_residual) AS amount_residual,
                SUM(account_move_line.balance) AS balance,
                SUM(account_move_line.amount_residual_currency) AS amount_residual_currency,
                SUM(account_move_line.amount_currency) AS amount_currency
            FROM ''' + tables + '''
            JOIN account_account account ON account.id = account_move_line.account_id
            WHERE ''' + where_clause + '''
            GROUP BY account_move_line.currency_id, account.reconcile
        ''', where_params)

        company_currency = self.company_id.currency_id
        journal_currency = self.currency_id if self.currency_id and self.currency_id != company_currency else False
        balance_currency = journal_currency or company_currency

        total_balance = 0.0
        nb_lines = 0
        for res in self._cr.dictfetchall():
            nb_lines += res['nb_lines']

            amount_currency = res['amount_residual_currency'] if res['is_account_reconcile'] else res['amount_currency']
            balance = res['amount_residual'] if res['is_account_reconcile'] else res['balance']

            if res['currency_id'] and journal_currency and res['currency_id'] == journal_currency.id:
                total_balance += amount_currency
            elif journal_currency:
                total_balance += company_currency._convert(balance, balance_currency, self.company_id, conversion_date)
            else:
                total_balance += balance
        return total_balance, nb_lines
    
    def _get_journal_bank_account_balance(self, domain=None):
        self.ensure_one()
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        self.env['account.move.line'].check_access_rights('read')

        if not self.default_account_id:
            return 0.0, 0

        domain = (domain or []) + [
            ('account_id', 'in', tuple(self.default_account_id.ids)),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('parent_state', '!=', 'cancel'),
            ('branch_id', 'in', branch_ids)
            ]
        query = self.env['account.move.line']._where_calc(domain)
        tables, where_clause, where_params = query.get_sql()

        query = '''
            SELECT
                COUNT(account_move_line.id) AS nb_lines,
                COALESCE(SUM(account_move_line.balance), 0.0),
                COALESCE(SUM(account_move_line.amount_currency), 0.0)
            FROM ''' + tables + '''
            WHERE ''' + where_clause + '''
        '''

        company_currency = self.company_id.currency_id
        journal_currency = self.currency_id if self.currency_id and self.currency_id != company_currency else False

        self._cr.execute(query, where_params)
        nb_lines, balance, amount_currency = self._cr.fetchone()
        return amount_currency if journal_currency else balance, nb_lines
    
    def _get_open_bills_to_pay_query(self):
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        return ('''
            SELECT
                (CASE WHEN move.move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * move.amount_residual AS amount_total,
                move.currency_id AS currency,
                move.move_type,
                move.invoice_date,
                move.company_id
            FROM account_move move
            WHERE move.journal_id = %(journal_id)s
            AND move.state = 'posted'
            AND move.payment_state in ('not_paid', 'partial')
            AND move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
            AND move.branch_id IN %(branch_ids)s;
        ''', {'journal_id': self.id, 'branch_ids': tuple(branch_ids)})

    def _get_draft_bills_query(self):
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        return ('''
            SELECT
                (CASE WHEN move.move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * move.amount_total AS amount_total,
                move.currency_id AS currency,
                move.move_type,
                move.invoice_date,
                move.company_id
            FROM account_move move
            WHERE move.journal_id = %(journal_id)s
            AND move.state = 'draft'
            AND move.payment_state in ('not_paid', 'partial')
            AND move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
            AND move.branch_id IN %(branch_ids)s;
        ''', {'journal_id': self.id, 'branch_ids': tuple(branch_ids)})

    def _get_late_bills_query(self):
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        return """
            SELECT
                (CASE WHEN move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * amount_residual AS amount_total,
                currency_id AS currency,
                move_type,
                invoice_date,
                company_id
            FROM account_move move
            WHERE journal_id = %(journal_id)s
            AND invoice_date_due < %(today)s
            AND state = 'posted'
            AND payment_state in ('not_paid', 'partial')
            AND move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
            AND move.branch_id IN %(branch_ids)s;
        """, {'journal_id': self.id, 'today': fields.Date.context_today(self), 'branch_ids': tuple(branch_ids)}
    
class AccountMove(models.Model):
    _inherit = 'account.move'
    
    def _get_move_display_name(self, show_ref=False):
        ''' Helper to get the display name of an invoice depending of its type.
        :param show_ref:    A flag indicating of the display name must include or not the journal entry reference.
        :return:            A string representing the invoice.
        '''
        self.ensure_one()
        name = ''
        if self.state == 'draft':
            name += {
                'out_invoice': _('Draft Invoice'),
                'out_refund': _('Draft Credit Note'),
                'in_invoice': _('Draft Bill'),
                'in_refund': _('Draft Debit Note'),
                'out_receipt': _('Draft Sales Receipt'),
                'in_receipt': _('Draft Purchase Receipt'),
                'entry': _('Draft Entry'),
            }[self.move_type]
            name += ' '
        if not self.name or self.name == '/':
            name += '(* %s)' % str(self.id)
        else:
            name += self.name
            if self.env.context.get('input_full_display_name'):
                if self.partner_id:
                    name += f', {self.partner_id.name}'
                if self.date:
                    name += f', {format_date(self.env, self.date)}'
        return name
    
    def get_formatted_value(self, amount):
        return formatLang(self.env, amount)
    
    def action_print_voucher(self):
        return self.env.ref('etl_account.action_report_voucher').report_action(self)
    
    def action_print_invoice(self):
        return self.env.ref('account.account_invoices_without_payment').report_action(self)
    
    def _search_default_journal(self):
        if self.payment_id and self.payment_id.journal_id:
            return self.payment_id.journal_id
        if self.statement_line_id and self.statement_line_id.journal_id:
            return self.statement_line_id.journal_id
        if self.statement_line_ids.statement_id.journal_id:
            return self.statement_line_ids.statement_id.journal_id[:1]

        if self.is_sale_document(include_receipts=True):
            journal_types = ['sale']
        elif self.is_purchase_document(include_receipts=True):
            journal_types = ['purchase']
        elif self.payment_id or self.env.context.get('is_payment'):
            journal_types = ['bank', 'cash']
        else:
            journal_types = ['general']

        company_id = (self.company_id or self.env.company).id
        domain = [('company_id', '=', company_id), ('type', 'in', journal_types)]

        journal = None
        currency_id = self.currency_id.id or self._context.get('default_currency_id')
        if currency_id and currency_id != self.company_id.currency_id.id:
            currency_domain = domain + [('currency_id', '=', currency_id)]
            journal = self.env['account.journal'].search(currency_domain, limit=1)

        if not journal:
            journal = self.env['account.journal'].search(domain, limit=1)

        if not journal:
            company = self.env['res.company'].browse(company_id)

            error_msg = _(
                "No journal could be found in company %(company_name)s for any of those types: %(journal_types)s",
                company_name=company.display_name,
                journal_types=', '.join(journal_types),
            )
            raise UserError(error_msg)
        if self.move_type == 'out_refund':
            journal = self.env.company.cn_journal_id
        if self.move_type == 'in_refund':
            journal = self.env.company.dn_journal_id
        return journal
    
    @api.depends('posted_before', 'state', 'journal_id', 'date', 'branch_id', 'move_name')
    def _compute_move_name(self):
        for move in self:
            move.name = move.move_name
    
    @api.depends('posted_before', 'state', 'journal_id', 'date', 'branch_id')
    def _compute_fiscal_year(self):
        for move in self:
            fiscal_year = ''
            if move.date:
                fy = move.company_id.compute_fiscalyear_dates(move.date)
                fiscal_year = fy['date_from'].strftime('%y') + fy['date_to'].strftime('%y')
            move.fiscal_year = fiscal_year
    
    @api.depends(
        'line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.balance',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state',
        'line_ids.full_reconcile_id',
        'state', 
        'recompute',
        'line_ids.debit',
        'line_ids.credit')
    def _compute_amount(self):
        for move in self:
            total_untaxed, total_untaxed_currency = 0.0, 0.0
            total_tax, total_tax_currency = 0.0, 0.0
            total_residual, total_residual_currency = 0.0, 0.0
            total, total_currency = 0.0, 0.0

            for line in move.line_ids:
                if move.is_invoice(True):
                    # === Invoices ===
                    if line.display_type == 'tax' or (line.display_type == 'rounding' and line.tax_repartition_line_id):
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type in ('product'):
                        # Untaxed amount.
                        total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type == 'payment_term':
                        # Residual amount.
                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                    elif line.display_type == 'rounding':
                        # total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            sign = move.direction_sign
            move.amount_untaxed = sign * total_untaxed_currency
            move.amount_tax = sign * total_tax_currency
            move.amount_total = sign * total_currency
            move.amount_residual = -sign * total_residual_currency
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = abs(total) if move.move_type == 'entry' else -total
            move.amount_residual_signed = total_residual
            move.amount_total_in_currency_signed = abs(move.amount_total) if move.move_type == 'entry' else -(sign * move.amount_total)
    
    @api.depends(
        'invoice_line_ids.currency_rate',
        'invoice_line_ids.tax_base_amount',
        'invoice_line_ids.tax_line_id',
        'invoice_line_ids.price_total',
        'invoice_line_ids.price_subtotal',
        'invoice_payment_term_id',
        'partner_id',
        'currency_id',
        'invoice_line_ids.discount_value',
        'invoice_line_ids.discount',
        'invoice_cash_rounding_id',
        'invoice_date',
        'state')
    def _compute_tax_totals(self):
        """ Computed field used for custom widget's rendering.
            Only set on invoices.
        """
        for move in self:
            dp = move.partner_id and move.partner_id.invoice_decimal or 2
            if move.is_invoice(include_receipts=True):
                base_lines = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
                base_line_values_list = [line._convert_to_tax_base_line_dict() for line in base_lines]
                if move.id:
                    sign = -1 if move.is_inbound(include_receipts=True) else 1
                    base_line_values_list += [
                        {
                            **line._convert_to_tax_base_line_dict(),
                            'handle_price_include': False,
                            'quantity': 1.0,
                            'price_unit': sign * line.amount_currency,
                        }
                        for line in move.line_ids.filtered(lambda line: line.display_type == 'epd')
                        ]

                kwargs = {
                    'base_lines': base_line_values_list,
                    'currency': move.currency_id or move.journal_id.currency_id or move.company_id.currency_id,
                    }

                if move.id:
                    kwargs['tax_lines'] = [
                        line._convert_to_tax_line_dict()
                        for line in move.line_ids.filtered(lambda line: line.display_type == 'tax')
                    ]
                else:
                    epd_aggregated_values = {}
                    for base_line in base_lines:
                        if not base_line.epd_needed:
                            continue
                        for grouping_dict, values in base_line.epd_needed.items():
                            epd_values = epd_aggregated_values.setdefault(grouping_dict, {'price_subtotal': 0.0})
                            epd_values['price_subtotal'] += values['price_subtotal']

                    for grouping_dict, values in epd_aggregated_values.items():
                        taxes = None
                        if grouping_dict.get('tax_ids'):
                            taxes = self.env['account.tax'].browse(grouping_dict['tax_ids'][0][2])

                        kwargs['base_lines'].append(self.env['account.tax']._convert_to_tax_base_line_dict(
                            None,
                            partner=move.partner_id,
                            currency=move.currency_id,
                            taxes=taxes,
                            price_unit=values['price_subtotal'],
                            quantity=1.0,
                            account=self.env['account.account'].browse(grouping_dict['account_id']),
                            analytic_distribution=values.get('analytic_distribution'),
                            price_subtotal=values['price_subtotal'],
                            is_refund=move.move_type in ('out_refund', 'in_refund'),
                            handle_price_include=False,
                        ))
                tax_totals = self.env['account.tax']._prepare_tax_totals(**kwargs)
                move.tax_totals = tax_totals
                rounding_line = move.line_ids.filtered(lambda l: l.display_type == 'rounding')
                if rounding_line:
                    balance = rounding_line.balance
                    if move.move_type in ('out_refund', 'in_invoice'):
                        balance = balance * -1
                    amount_total_rounded = move.tax_totals['amount_total'] - balance
                    move.tax_totals['formatted_amount_total_rounded'] = formatLang(self.env, amount_total_rounded, digits=dp, currency_obj=move.currency_id) or ''
            else:
                move.tax_totals = None
    
    def _recompute_cash_rounding_lines(self):
        self.ensure_one()
        
        def _compute_cash_rounding(self, total_amount_currency):
            dp_dic = {2: 0.01, 3: 0.001}
            dp = dp_dic[self.partner_id.invoice_decimal]
            difference = self.invoice_cash_rounding_id.compute_difference(self.currency_id, total_amount_currency)
            difference = round(tools.float_round(difference, precision_rounding=dp), self.partner_id.invoice_decimal)
            if self.currency_id == self.company_id.currency_id:
                diff_amount_currency = diff_balance = difference
            else:
                diff_amount_currency = difference
                diff_balance = self.currency_id._convert(diff_amount_currency, self.company_id.currency_id, self.company_id, self.invoice_date or self.date)
            # logger.info('-'*75)
            # logger.info('_compute_cash_rounding:%s-%s'%(diff_balance, diff_amount_currency))
            # logger.info('-'*75)
            return diff_balance, diff_amount_currency

        def _apply_cash_rounding(self, diff_balance, diff_amount_currency, cash_rounding_line):
            rounding_line_vals = {
                'balance': diff_balance,
                'partner_id': self.partner_id.id,
                'move_id': self.id,
                'currency_id': self.currency_id.id,
                'company_id': self.company_id.id,
                'company_currency_id': self.company_id.currency_id.id,
                'display_type': 'rounding',
                }

            if self.invoice_cash_rounding_id.strategy == 'biggest_tax':
                biggest_tax_line = None
                for tax_line in self.line_ids.filtered('tax_repartition_line_id'):
                    if not biggest_tax_line or tax_line.price_subtotal > biggest_tax_line.price_subtotal:
                        biggest_tax_line = tax_line

                # No tax found.
                if not biggest_tax_line:
                    return

                rounding_line_vals.update({
                    'name': _('%s (rounding)', biggest_tax_line.name),
                    'account_id': biggest_tax_line.account_id.id,
                    'tax_repartition_line_id': biggest_tax_line.tax_repartition_line_id.id,
                    'tax_tag_ids': [(6, 0, biggest_tax_line.tax_tag_ids.ids)],
                    'tax_ids': [Command.set(biggest_tax_line.tax_ids.ids)]
                    })

            elif self.invoice_cash_rounding_id.strategy == 'add_invoice_line':
                if diff_balance > 0.0 and self.invoice_cash_rounding_id.loss_account_id:
                    account_id = self.invoice_cash_rounding_id.loss_account_id.id
                else:
                    account_id = self.invoice_cash_rounding_id.profit_account_id.id
                rounding_line_vals.update({
                    'name': self.invoice_cash_rounding_id.name,
                    'account_id': account_id,
                    'tax_ids': [Command.clear()]
                    })

            # Create or update the cash rounding line.
            if cash_rounding_line:
                cash_rounding_line.write(rounding_line_vals)
            else:
                cash_rounding_line = self.env['account.move.line'].create(rounding_line_vals)

        existing_cash_rounding_line = self.line_ids.filtered(lambda line: line.display_type == 'rounding')

        # The cash rounding has been removed.
        if not self.invoice_cash_rounding_id:
            existing_cash_rounding_line.unlink()
            # self.line_ids -= existing_cash_rounding_line
            return

        # The cash rounding strategy has changed.
        if self.invoice_cash_rounding_id and existing_cash_rounding_line:
            strategy = self.invoice_cash_rounding_id.strategy
            old_strategy = 'biggest_tax' if existing_cash_rounding_line.tax_line_id else 'add_invoice_line'
            if strategy != old_strategy:
                # self.line_ids -= existing_cash_rounding_line
                existing_cash_rounding_line.unlink()
                existing_cash_rounding_line = self.env['account.move.line']

        others_lines = self.line_ids.filtered(lambda line: line.account_id.account_type not in ('asset_receivable', 'liability_payable'))
        others_lines -= existing_cash_rounding_line
        total_amount_currency = sum(others_lines.mapped('amount_currency'))

        diff_balance, diff_amount_currency = _compute_cash_rounding(self, total_amount_currency)

        # The invoice is already rounded.
        if self.currency_id.is_zero(diff_balance) and self.currency_id.is_zero(diff_amount_currency):
            existing_cash_rounding_line.unlink()
            # self.line_ids -= existing_cash_rounding_line
            return
        # logger.info('-'*75)
        # logger.info('_apply_cash_rounding:%s-%s'%(diff_balance, diff_amount_currency))
        # logger.info('#'*75)
        _apply_cash_rounding(self, diff_balance, diff_amount_currency, existing_cash_rounding_line)
        
    @api.onchange('transporter_id')
    def onchange_transporter_id(self):
        if self.transporter_id:
            self.transgst = self.transporter_id.gst
        else:
            self.transgst = ''
    
    def _compute_ewb(self):
        for move in self:
            if move.move_type == 'out_invoice':
                if move.amount_total_signed > 50000:
                    move.need_ewb = True
                else:
                    move.need_ewb = False
            else:
                move.need_ewb = False
                
    fiscal_year = fields.Char('Fiscal Year', compute='_compute_fiscal_year', store=True)
    sales_executive_id = fields.Many2one('hr.employee', 'Sales Executive')
    zonal_head_id = fields.Many2one('hr.employee', 'Zonal Head')
    region_id = fields.Many2one('sales.region', 'Region')
    so_id = fields.Many2one('sale.order', 'Sales Order')
    name = fields.Char('Number', copy=False, tracking=True, default='/')
    move_name = fields.Char('Move Name', default='/', copy=False)
    tax_totals = fields.Binary("Invoice Totals", compute='_compute_tax_totals',
        inverse='_inverse_tax_totals', exportable=False)
    branch_move_id = fields.Many2one('account.move', 'Branch Move', copy=False)
    is_branch_invoice = fields.Boolean('Stock Transfer Entry', compute='_branch_move', store=True)
    
    distance = fields.Integer("Distance", tracking=True, copy=False)
    vehicle_type = fields.Selection([
        ("R", "Regular"),
        ("O", "ODC")],
        string="Vehicle Type", copy=False, tracking=True)
    trans_mode = fields.Selection([
        ("0", "Managed by Transporter"),
        ("1", "By Road"),
        ("2", "Rail"),
        ("3", "Air"),
        ("4", "Ship")],
        string="Transportation Mode", copy=False, tracking=True)
    transporter_id = fields.Many2one("eway.transporter", 'Transporter', copy=False, tracking=True)
    transportation_doc_no = fields.Char(
        string="E-waybill Document Number",
        help="""Transport document number. If it is more than 15 chars, last 15 chars may be entered""",
        copy=False, tracking=True)
    transportation_doc_date = fields.Date(
        string="Document Date",
        help="Date on the transporter document",
        copy=False,
        tracking=True)
    transaction_id = fields.Char("Transaction ID", copy=False, tracking=True)
    vehicle_no = fields.Char("Vehicle Number", copy=False, tracking=True)
    
    irn_no = fields.Char("IRN No.", copy=False)
    irn_ack_no = fields.Char("IRN Ack. No.", copy=False)
    irn_ack_date = fields.Date("IRN Ack. Date", copy=False)
    signed_einvoice = fields.Char("Signed Invoice", copy=False)
    signed_qrcode = fields.Char("Signed QR", copy=False)
    irn_success = fields.Char("IRN Success", copy=False)
    log = fields.Char("IRN Status", copy=False, tracking=True)
    govt_log = fields.Char("Government Log", copy=False)
    qr_code = fields.Binary("Signed QRCode", attachment=True, store=True, copy=False)
    ob = fields.Boolean('OB', compute='_compute_ob', store=True)
    booking_dest = fields.Char('Booking Destination')
    need_ewb = fields.Boolean(compute='_compute_ewb')
    ewb_no = fields.Char("EWB No", copy=False, tracking=True)
    ewb_date = fields.Char("EWB Date", copy=False)
    ewb_exp_date = fields.Char("EWB Exp Date", copy=False)
    ewb_update_date = fields.Char("EWB Update Date", copy=False)
    elog = fields.Char("EWB Log", copy=False)
    ewb_status = fields.Char("EWB Status", copy=False, tracking=True)
    transgst = fields.Char("Transporter GST", copy=False)
    recompute = fields.Boolean()
    amount_untaxed = fields.Monetary(
        string='Untaxed Amount',
        compute='_compute_amount', store=True, readonly=True,
        tracking=True)
    amount_tax = fields.Monetary(
        string='Tax',
        compute='_compute_amount', store=True, readonly=True)
    amount_total = fields.Monetary(
        string='Total',
        compute='_compute_amount', store=True, readonly=True,
        inverse='_inverse_amount_total')
    amount_residual = fields.Monetary(
        string='Amount Due',
        compute='_compute_amount', store=True)
    amount_untaxed_signed = fields.Monetary(
        string='Untaxed Amount Signed',
        compute='_compute_amount', store=True, readonly=True,
        currency_field='company_currency_id')
    amount_tax_signed = fields.Monetary(
        string='Tax Signed',
        compute='_compute_amount', store=True, readonly=True,
        currency_field='company_currency_id')
    amount_total_signed = fields.Monetary(
        string='Total Signed',
        compute='_compute_amount', store=True, readonly=True,
        currency_field='company_currency_id')
    amount_total_in_currency_signed = fields.Monetary(
        string='Total in Currency Signed',
        compute='_compute_amount', store=True, readonly=True,
        currency_field='currency_id')
    amount_residual_signed = fields.Monetary(
        string='Amount Due Signed',
        compute='_compute_amount', store=True,
        currency_field='company_currency_id')
    pctr_bag = fields.Integer(compute='_compute_package_data')
    pctr_belt = fields.Integer(compute='_compute_package_data')
    pctr_weight = fields.Float(compute='_compute_package_data')
    bg_bag = fields.Integer(compute='_compute_package_data')
    bg_box = fields.Integer(compute='_compute_package_data')
    bg_roll = fields.Integer(compute='_compute_package_data')
    bg_weight = fields.Float(compute='_compute_package_data')
    bvc_drum = fields.Integer(compute='_compute_package_data')
    bvc_can = fields.Integer(compute='_compute_package_data')
    bvc_ltr = fields.Integer(compute='_compute_package_data')
    bvc_weight = fields.Float(compute='_compute_package_data')
    ct_bag = fields.Integer(compute='_compute_package_data')
    ct_belt = fields.Integer(compute='_compute_package_data')
    ct_weight = fields.Float(compute='_compute_package_data')
    tag_id = fields.Many2one('crm.tag', 'Tag', compute='_compute_tag', store=True)
    so_type = fields.Selection([
        ('export', 'Export Sales'),
        ('domestic', 'Domestic Sales'),
        ('direct', 'RTC Sales'),
        ('stock', 'Stock Transfer Sales'),
        ('internal', 'Internal Transfer'),
        ('trade', 'Traded Product Sales'),
        ('rt_sales', 'Retreading Sales'),
        ('service', 'Services'),
        ('foc', 'FOC'),
        ('scrap', 'Scrap Sales'),
        ('seconds', 'Seconds Sales'),
        ('none', 'None')
        ], 'Sales Order Type', compute='_comoute_so_type', store=True)
    rt_sales = fields.Boolean('Retreading Sales')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    allow_invoice_editing = fields.Boolean('Allow Lines Editing', compute='_check_inv_access')
    new_journal_id = fields.Many2one('account.journal', 'New Journal')
    bank_date = fields.Date('Bank Date', compute='_compute_bank_date', store=True)
    posted_date = fields.Datetime('Posted Date & Time', copy=False)
    move_type = fields.Selection(
        selection=[
            ('entry', 'Journal Entry'),
            ('out_invoice', 'Customer Invoice'),
            ('out_refund', 'Credit Note'),
            ('in_invoice', 'Vendor Bill'),
            ('in_refund', 'Debit Note'),
            ('out_receipt', 'Sales Receipt'),
            ('in_receipt', 'Purchase Receipt'),
            ],
        string='Type', required=True, readonly=True, 
        tracking=True, change_default=True, index=True, default="entry")
    dn_type = fields.Selection([('customer', 'Customer Debit Note'), ('vendor', 'Vendor Debit Note')], string='Debit Note Type')
    cn_type = fields.Selection([('customer', 'Customer Credit Note'), ('vendor', 'Vendor Credit Note')], string='Credit Note Type')
    
    @api.model
    def get_sale_types(self, include_receipts=False):
        sale_types = ['out_invoice', 'out_refund'] + (include_receipts and ['out_receipt'] or [])
        return sale_types

    def is_sale_document(self, include_receipts=False):
        sale_document = self.move_type in self.get_sale_types(include_receipts)
        return sale_document
    
    def is_customer_doc(self):
        if self.move_type == 'out_invoice':
            return True
        else:
            if self.move_type == 'out_refund':
                if self.cn_type == 'customer':
                    return True
                else:
                    return False
            elif self.move_type == 'in_refund':
                if self.dn_type == 'customer':
                    return True
                else:
                    return False
        return False

    @api.model
    def get_purchase_types(self, include_receipts=False):
        purchase_types = ['in_invoice', 'in_refund'] + (include_receipts and ['in_receipt'] or [])
        return purchase_types

    def is_purchase_document(self, include_receipts=False):
        purchase_document = self.move_type in self.get_purchase_types(include_receipts)
        return purchase_document
    
    def is_vendor_doc(self):
        if self.move_type == 'in_invoice':
            return True
        else:
            if self.move_type == 'out_refund':
                if self.cn_type == 'vendor':
                    return True
                else:
                    return False
            elif self.move_type == 'in_refund':
                if self.dn_type == 'vendor':
                    return True
                else:
                    return False
        return False


    @api.depends('state', 'line_ids', 'line_ids.bank_date')
    def _compute_bank_date(self):
        for move in self:
            if move.state == 'posted':
                amls = self.env['account.move.line'].search([
                    ('account_id', '=', move.journal_id.default_account_id.id),
                    ('move_id', '=', move.id)
                    ])
                if amls and amls[0].bank_date:
                    move.bank_date = amls[0].bank_date
                move.bank_date = False
            else:
                move.bank_date = False
                
    def action_change_journal(self):
        for move in self:
            if move.new_journal_id:
                self._cr.execute("""update account_move set journal_id=%s where id=%s"""% (self.new_journal_id.id, self.id))
                for line in move.line_ids:
                    self._cr.execute("""update account_move_line set journal_id=%s where id=%s"""% (self.new_journal_id.id, line.id))
        return True
    
    @api.depends('journal_id', 'company_id.ob_journal_id')
    def _compute_ob(self):
        for move in self:
            if move.journal_id and move.journal_id.id == move.company_id.ob_journal_id.id: 
                move.ob = True
            else:
                move.ob = False
    
    def _check_inv_access(self):
        for move in self:
            allow_editing = False
            if move.state == 'draft':
                if move.move_type in ('out_refund', 'in_refund'):
                    allow_editing = True
                else:
                    if self.user_has_groups('etl_base.group_invoice_editing'):
                        allow_editing = True
            move.allow_invoice_editing = allow_editing

    def _login_user(self):
        for move in self:
            move.login_user_id = self.env.user.user_access and self.env.user.id or False
            
    @api.depends('so_id', 'so_id.so_type', 'recompute', 'rt_sales')
    def _comoute_so_type(self):
        for move in self:
            move.so_type = (move.rt_sales and 'rt_sales') or (move.so_id and move.so_id.so_type or 'none')
                
    @api.depends('partner_id', 'partner_id.tag_id')
    def _compute_tag(self):
        for move in self:
            if move.move_type == 'out_invoice' and move.partner_id and move.partner_id.tag_id:
                move.tag_id = move.partner_id.tag_id.id
            else:
                move.tag_id = False

    def _compute_package_data(self):
        for move in self:
            pctr_bag, pctr_belt, pctr_weight = 0, 0, 0
            bg_bag, bg_box, bg_roll, bg_weight = 0, 0, 0, 0
            bvc_drum, bvc_can, bvc_ltr, bvc_weight = 0, 0, 0, 0
            ct_bag, ct_belt, ct_weight = 0, 0, 0
            if move.invoice_line_ids:
                for line in move.invoice_line_ids:
                    if line.alt_uom_id:
                        uom = line.alt_uom_id.name
                        if line.product_id.detailed_type != 'service':
                            fg_type = line.product_id.categ_id.fg_type
                            if fg_type == 'pctr':
                                pctr_weight += line.quantity
                                if uom == 'BAG':
                                    pctr_bag += line.alt_uom_qty
                                elif uom == 'BELTS':
                                    pctr_belt += line.alt_uom_qty
                            elif fg_type == 'bg':
                                bg_weight += line.quantity
                                if uom == 'BAG':
                                    bg_bag += line.alt_uom_qty
                                elif uom == 'BOX':
                                    bg_box += line.alt_uom_qty
                                elif uom == 'ROLL':
                                    bg_roll += line.alt_uom_qty
                            elif fg_type == 'bvc':
                                bvc_weight += line.quantity
                                if uom == 'DRUM':
                                    bvc_drum += line.alt_uom_qty
                                elif uom == 'CAN':
                                    bvc_can += line.alt_uom_qty
                                elif uom == 'LTR':
                                    bvc_ltr += line.alt_uom_qty
                            elif fg_type == 'ct':
                                ct_weight += line.quantity
                                if uom == 'BAG':
                                    ct_bag += line.alt_uom_qty
                                elif uom == 'BELTS':
                                    ct_belt += line.alt_uom_qty
            move.pctr_bag = round(pctr_bag, 2)
            move.pctr_belt = round(pctr_belt, 2)
            move.pctr_weight = round(pctr_weight, 2)

            move.bg_bag = round(bg_bag, 2)
            move.bg_box = round(bg_box, 2)
            move.bg_roll = round(bg_roll, 2)
            move.bg_weight = round(bg_weight, 2)

            move.bvc_drum = round(bvc_drum, 2)
            move.bvc_can = round(bvc_can, 2)
            move.bvc_ltr = round(bvc_ltr, 2)
            move.bvc_weight = round(bvc_weight, 2)

            move.ct_bag = round(ct_bag, 2)
            move.ct_belt = round(ct_belt, 2)
            move.ct_weight = round(ct_weight, 2)
                                
    @api.depends('partner_id', 'partner_id.is_branch')
    def _branch_move(self):
        for move in self:
            if move.partner_id and move.move_type in ('out_invoice', 'in_invoice'):
                move.is_branch_invoice = move.partner_id.is_branch
                
    def _post(self, soft=True):
        for move in self:
            move_name = move.find_next_number()
            move.name = move_name
            move.move_name = move_name
            # for line in move.line_ids:
            #     if line.account_id.account_type == 'asset_cash' and line.credit > line.account_id.current_balance:
            #         raise UserError('Cannot have negative balance on %s'%(line.account_id.name))
            if move.move_type == 'out_invoice' and move.partner_id.use_partner_credit_limit:
                total_amount  = move.partner_id.credit + move.amount_total_signed
                if total_amount > move.partner_id.credit_limit:
                    raise UserError('Credit Limit exceeded for this Customer.')
                credit_days = move.partner_id.credit_period_days
                if credit_days > 0 and move.partner_id.credit > 0:
                    amls = self.env['account.move.line'].search([
                        ('parent_state', '=', 'posted'), 
                        ('amount_residual', '!=', 0),
                        ('partner_id', '=', self.partner_id.id), 
                        ('account_id.reconcile', '=', True),
                        ('debit', '>', 0)
                        ])
                    for aml in amls:
                        due_date = (aml.date + timedelta(days=credit_days)).strftime('%Y-%m-%d')
                        if due_date < fields.Date.today().strftime('%Y-%m-%d'):
                            raise UserError('Credit Period already exceeded for this Customer.')
        res = super(AccountMove, self)._post()
            
        for move in self:
            if move.partner_id.is_branch:
                if move.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                    partner = move.partner_id
                    acc_ids = [partner.property_account_receivable_id.id, partner.property_account_payable_id.id]
                    for inv_line in move.invoice_line_ids:
                        acc_ids.append(inv_line.account_id.id) 
                    if move.invoice_cash_rounding_id:
                        if move.invoice_cash_rounding_id.profit_account_id:
                            acc_ids.append(move.invoice_cash_rounding_id.profit_account_id.id)
                        if move.invoice_cash_rounding_id.loss_account_id:
                            acc_ids.append(move.invoice_cash_rounding_id.loss_account_id.id)
                    acc_ids = list(set(acc_ids))
                    lines = []
                    for line in move.line_ids:
                        debit = line.credit
                        credit = line.debit
                        if line.account_id.id in acc_ids:
                            account_id = line.account_id.id
                        else:
                            account_id = move.company_id.branch_acc_id.id
                        if move.move_type == 'out_invoice':
                            name = 'Stock Transfer Invoice reversal'
                        elif move.move_type == 'out_refund':
                            name = 'Stock Transfer Credit Note reversal'
                        elif move.move_type == 'in_invoice':
                            name = 'Stock Transfer Purchase Bill reversal'
                        elif move.move_type == 'in_refund':
                            name = 'Stock Transfer Debit Note reversal'
                        line_vals = {
                            'name': name,
                            'debit': debit,
                            'credit': credit,
                            'account_id': account_id,
                            }
                        lines.append((0, 0, line_vals))
                    move_vals = {
                        'journal_id': move.company_id.branch_journal_id.id,
                        'line_ids': lines,
                        'date': self.invoice_date,
                        'move_type': 'entry',
                        'partner_id': move.partner_id.id,
                        'branch_id': move.branch_id.id
                        }
                    if move.branch_move_id:
                        move.branch_move_id.write(move_vals)
                        move.branch_move_id._post()
                    else:
                        account_move = self.env['account.move'].sudo().create(move_vals)
                        move.branch_move_id = account_move.id
                        account_move._post()
            if not move.posted_date:
                move.posted_date = fields.Datetime.now()
        return res
    
    def find_next_number(self):
        self.ensure_one()
        move = self
        new_code = False
        fiscal_year = move.fiscal_year
        name = move.move_name
        branch_code = move.branch_id.code
        if name != '/' and not move.ob:
            ex_code = name.split('/')[2]
            if branch_code != ex_code:
                new_code = True
        if name == '/' or new_code:
            code_dic = {'export': 'EX', 'rt_sales': 'RT', 'stock': 'ST', 'service': 'SR'}
            code_list = list(code_dic.keys())
            if move.move_type == 'out_invoice':
                code = code_dic.get(move.so_type, move.journal_id.code)
            else:
                code = move.journal_id.code
            seq_prefix = '%s/%s/%s'%(code, fiscal_year, move.branch_id.code)
            if move.move_type == 'out_invoice':
                if move.so_type in code_list:
                    prev_moves = self.with_context(no_filter=True).search([
                        ('journal_id', '=', move.journal_id.id),
                        ('branch_id', '=', move.branch_id.id),
                        ('fiscal_year', '=', move.fiscal_year),
                        ('move_name', '!=', '/'),
                        ('id', '!=', move.id),
                        ('so_type', '=', move.so_type)
                        ], order='move_name desc', limit=1)
                else:
                    prev_moves = self.with_context(no_filter=True).search([
                        ('journal_id', '=', move.journal_id.id),
                        ('branch_id', '=', move.branch_id.id),
                        ('fiscal_year', '=', move.fiscal_year),
                        ('move_name', '!=', '/'),
                        ('id', '!=', move.id),
                        ('so_type', 'not in', code_list)
                        ], order='move_name desc', limit=1)
            else:
                prev_moves = self.with_context(no_filter=True).search([
                    ('journal_id', '=', move.journal_id.id),
                    ('branch_id', '=', move.branch_id.id),
                    ('fiscal_year', '=', move.fiscal_year),
                    ('move_name', '!=', '/'),
                    ('id', '!=', move.id),
                    ('move_name', 'ilike', seq_prefix)
                    ], order='move_name desc', limit=1)
            if prev_moves:
                prev_name = prev_moves[0].move_name
                if '/' in prev_name:
                    name_split = prev_name.split('/')[-1]
                    sequence_number = int(name_split) + 1
                else:
                    sequence_number = 1
            else:
                sequence_number = 1
            if move.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                name = '%s/%s'%(seq_prefix, str(sequence_number).zfill(4))
            else:
                name = '%s/%s'%(seq_prefix, str(sequence_number).zfill(6))
        return name
    
    def action_correct_tax_entries(self):
        for move in self:
            move.button_draft()
            lines = []
            for line in move.line_ids:
                if line.tax_ids and line.tax_tag_ids:
                    lines.append(line)
                else:
                    self._cr.execute('delete from account_move_line where id=%s'% (line.id))
            for line in lines:
                    line.tax_ids = False
                    line.tax_tag_ids = False
            move.action_post()
        return True
    
    def action_correct_tax_entries2(self):
        for move in self:
            for line in move.line_ids:
                if line.account_id.id not in (5003, 5457):
                    self._cr.execute('delete from account_move_line where id=%s'% (line.id))
            move.action_post()
        return True
    
    def check_editing_access(self):
        for move in self:
            if not move.posted_date:
                posted_date = False
                messages = self.env['mail.message'].sudo().search([
                    ('res_id', '=', move.id),
                    ('model', '=', 'account.move')
                    ])
                for message in messages:
                    for tracking in message.tracking_value_ids:
                        if tracking.field_desc == 'Status' and tracking.new_value_char == 'Posted':
                            posted_date = message.date
                            break
                    if posted_date:
                        break
                if posted_date:
                    move.posted_date = posted_date
            if move.posted_date:
                diff = fields.Datetime.now() - move.posted_date
                two_days = 48 * 60 * 60
                total_seconds = diff.seconds + diff.days * 60 * 60 * 24
                allowed = True
                if total_seconds > two_days:
                    if move.move_type == 'out_invoice':
                        if not self.user_has_groups('etl_base.group_inv_editing'):
                            allowed = False
                    elif move.move_type == 'out_refund':
                        if not self.user_has_groups('etl_base.group_cn_editing'):
                            allowed = False
                    elif move.move_type == 'in_invoice':
                        if not self.user_has_groups('etl_base.group_vb_editing'):
                            allowed = False
                    elif move.move_type == 'in_refund':
                        if not self.user_has_groups('etl_base.group_dn_editing'):
                            allowed = False
                    else:
                        if move.payment_id:
                            if move.payment_id.partner_type == 'customer':
                                if not self.user_has_groups('etl_base.group_cp_editing'):
                                    allowed = False
                            elif move.payment_id.partner_type == 'supplier':
                                if not self.user_has_groups('etl_base.group_vp_editing'):
                                    allowed = False
                        else:
                            if not self.user_has_groups('etl_base.group_move_editing'):
                                allowed = False
                    if not allowed:
                        raise UserError('Editing Not allowed after 48 Hours !')
        return True
    
    def button_draft(self):
        self.check_editing_access()
        res = super(AccountMove, self).button_draft()
        for move in self:
            if move.branch_move_id:
                move.branch_move_id.state = 'draft'
                move.branch_move_id.line_ids.unlink()
        return res
    
    def button_cancel(self):
        self.check_editing_access()
        res = super(AccountMove, self).button_cancel()
        for move in self:
            if move.branch_move_id:
                move.branch_move_id.state = 'draft'
                move.branch_move_id.line_ids.unlink()
        return res
    
    def _inverse_tax_totals(self):
        if self.env.context.get('skip_invoice_sync'):
            return
        with self._sync_dynamic_line(
            existing_key_fname='term_key',
            needed_vals_fname='needed_terms',
            needed_dirty_fname='needed_terms_dirty',
            line_type='payment_term',
            container={'records': self},
        ):
            for move in self:
                if not move.is_invoice(include_receipts=True):
                    continue
                invoice_totals = move.tax_totals

                for amount_by_group_list in invoice_totals['groups_by_subtotal'].values():
                    for amount_by_group in amount_by_group_list:
                        tax_lines = move.line_ids.filtered(lambda line: line.tax_group_id.id == amount_by_group['tax_group_id'])

                        if tax_lines:
                            first_tax_line = tax_lines[0]
                            tax_group_old_amount = sum(tax_lines.mapped('amount_currency'))
                            sign = -1 if move.is_inbound() else 1
                            delta_amount = tax_group_old_amount * sign - amount_by_group['tax_group_amount']

                            if not move.currency_id.is_zero(delta_amount):
                                first_tax_line.amount_currency -= delta_amount * sign
            self._compute_amount()
            
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        res = super(AccountMove, self)._onchange_partner_id()
        if self.partner_id:
            self.sales_executive_id = self.partner_id.sales_executive_id and self.partner_id.sales_executive_id.id or False
            self.zonal_head_id = self.partner_id.zonal_head_id and self.partner_id.zonal_head_id.id or False
        return res
    
    def check_backdated_access(self, entry_date):
        current_date = fields.Date.today()
        if isinstance(entry_date, str):
            entry_date = datetime.strptime(entry_date, '%Y-%m-%d').date()
        access_1day = self.user_has_groups('etl_base.group_backdate_1day')
        access_3day = self.user_has_groups('etl_base.group_backdate_3day')
        access_cmonth = self.user_has_groups('etl_base.group_backdate_cmonth')
        access_month = self.user_has_groups('etl_base.group_backdate_month')
        access_unlimited = self.user_has_groups('etl_base.group_backdate_unlimited')
        cd_str, ed_str = current_date.strftime('%Y%m%d'), entry_date.strftime('%Y%m%d')
        cm_str, em_str = current_date.strftime('%Y%m'), entry_date.strftime('%Y%m')
        pm_str = (datetime.strptime(current_date.strftime('%Y-%m-01'), '%Y-%m-%d') - timedelta(days=1)).strftime('%Y%m')
        warning_msg = UserError("You don't have access to enter back-dated entry !")
        if cd_str == ed_str:
            return True
        else:
            if self.move_type in ('out_invoice', 'out_refund', 'in_refund') and cd_str != ed_str:
                if access_unlimited:
                    return True
                else:
                    type_dic = {'out_invoice': 'Sales Invoice', 'out_refund': 'Credit Note', 'in_refund': 'Debit Note'}
                    raise UserError("Back-dated entry not allowed for %s!"%(type_dic[self.move_type]))
            else:
                if access_unlimited:
                    return True
                if not access_1day and not access_3day and not access_month and not access_unlimited and not access_cmonth:
                    raise warning_msg
                diff = (current_date - entry_date).days
                if cm_str == em_str:
                    if diff == 1:
                        if access_1day:
                            return True
                        else:
                            raise warning_msg
                    elif diff in [1, 2, 3]:
                        if access_3day:
                            return True
                        else:
                            raise warning_msg
                    elif diff > 3:
                        if access_unlimited or access_cmonth:
                            return True
                        else:
                            raise warning_msg
                elif cm_str != em_str:
                    if access_unlimited:
                        return True
                    else:
                        if pm_str == em_str:
                            if not access_month:
                                raise warning_msg
                        else:
                            raise warning_msg
        return True
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'date' in vals:
                self.check_backdated_access(vals['date'])
        res = super(AccountMove, self).create(vals_list)
        return res
    
    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        for move in self:
            move.check_backdated_access(move.date.strftime('%Y-%m-%d'))
        return res
    
    def action_mark_irn_cancelled(self):
        for move in self:
            move.irn_no = ''
            move.irn_ack_date = False
            move.irn_ack_no = ''
            move.log = 'IRN_CANCELLED'
            move.qr_code = False
        return True
    
    def action_mark_ewb_cancelled(self):
        for move in self:
            move.ewb_no = ''
            move.ewb_date = ''
            move.ewb_exp_date = ''
            move.ewb_update_date = ''
            move.ewb_status = 'CANCELLED'
            move.elog = ''
        return True
    
    def action_generate_irn(self):
        company = self.env['res.company'].browse(1)
        access_token = company.irn_access_token
        url = company.irn_url
        buyer = self.partner_id
        if buyer.l10n_in_gst_treatment == 'overseas':
            buyer_gstin = 'URP'
            buyer_state_code = '96'
            buyer_pin = 999999
            supply_type = "EXPWOP"
        else:
            buyer_gstin = buyer.vat
            if not buyer_gstin:
                raise UserError('Please enter GSTN in Customer')
            buyer_state_code = buyer_gstin[0:2]
            buyer_pin = buyer.zip
            supply_type = "B2B"
        
        seller = self.branch_id.partner_id
        if not seller.vat:
            raise UserError('Please enter GSTN in Branch')
        seller_gstin = seller.vat
        seller_state_code = seller_gstin[0:2]
        
        item_list = []
        count = 1
        total_untaxed, total_gst, total_igst, total_tcs, total_amount = 0, 0, 0, 0, 0
        dp_dic = {2: 0.01, 3: 0.001}
        dp = dp_dic[buyer.invoice_decimal]
        for line in self.invoice_line_ids:
            gst_rate, gst_amount, igst_amount, tcs_amount = 0.0, 0.0, 0.0, 0.0 
            taxable_value = line.price_subtotal
            logger.info('-'*75)
            logger.info('taxable_value:%s'%taxable_value)
            for tax in line.tax_ids:
                group = tax.tax_group_id.name 
                if group == 'GST':
                    gst_rate = tax.amount
                    gst_amount = round(tools.float_round(taxable_value * gst_rate * 0.01/2, precision_rounding=dp), buyer.invoice_decimal)
                if group == 'IGST':
                    gst_rate = tax.amount
                    igst_amount = round(tools.float_round(taxable_value * gst_rate * 0.01, precision_rounding=dp), buyer.invoice_decimal)
                elif group == 'TCS':
                    tcs_base = taxable_value + gst_amount*2 + igst_amount
                    logger.info('tcs_base:%s'%tcs_base)
                    tcs_amount = round(tools.float_round(tcs_base * tax.amount * 0.01, precision_rounding=dp), buyer.invoice_decimal)
                    logger.info('tcs_amount:%s'%tcs_amount)
            total = line.price_total
            total = round(tools.float_round(total, precision_rounding=dp), buyer.invoice_decimal)
            IsServc = "N"
            if line.product_id.detailed_type == "service":
                IsServc = "Y"
            price_unit = line.price_unit * (1 - 0.01 * line.discount)
            price_unit = round(tools.float_round(price_unit, precision_rounding=dp), buyer.invoice_decimal)
            price_unit_disc = price_unit - line.discount_value
            price_unit = round(tools.float_round(price_unit_disc, precision_rounding=dp), buyer.invoice_decimal)
            item_dict = {
                "SlNo": count,
                "ProdName": line.name,
                "IsServc": IsServc,
                "HsnCd": line.product_id.hs_code_id.name,
                "Qty": line.quantity,
                "Unit": "NOS",
                "UnitPrice": price_unit,
                "TotAmt": line.price_subtotal,
                "Discount": 0,
                "AssAmt": line.price_subtotal,
                "GstRt": gst_rate,
                "IgstAmt": igst_amount,
                "CgstAmt": gst_amount,
                "SgstAmt": gst_amount,
                "OthChrg": tcs_amount,
                "TotItemVal": total,
                }
            
            # logger.info(item_dict)
            # logger.info('#'*75)
            count = count + 1
            total_untaxed += taxable_value
            total_gst += gst_amount
            total_igst += igst_amount
            total_tcs += tcs_amount
            total_amount += total
            item_list.append(item_dict)

        rounding_line = self.line_ids.filtered(lambda l: l.display_type == 'rounding')
        round_off = 0
        if rounding_line:
            round_off = -1 * rounding_line.balance
        total_tcs = round(tools.float_round(total_tcs, precision_rounding=dp), buyer.invoice_decimal)
        total_amount = round(total_amount + round_off, buyer.invoice_decimal)
        seller_details = {
            "Gstin": seller_gstin,
            "LglNm": company.legal_name,
            "TrdNm": company.trade_name,
            "Addr1": seller.street,
            "Loc": seller.state_id.name,
            "Pin": seller.zip,
            "Stcd": seller_state_code,
            }
        buyer_details = {
            "Gstin": buyer_gstin,
            "LglNm": buyer.name,
            "TrdNm": buyer.name,
            "Pos": buyer_state_code,
            "Addr1": buyer.street,
            "Loc": buyer.street2,
            "Pin": buyer_pin,
            "Stcd": buyer_state_code,
            }
        value_details = {
            "AssVal": total_untaxed,
            "CgstVal": total_gst,
            "SgstVal": total_gst,
            "IgstVal": total_igst,
            "Discount": 0,
            "OthChrg": 0,
            "TotInvVal": total_amount,
            "TotInvValFc": total_amount,
            "RndOffAmt": round_off
            }
        types = {"out_invoice": "INV", "out_refund": "CRN", "in_refund": "DBN"}
        doc_type = types[self.move_type]
        doc_details = {
            "Typ": doc_type,
            "No": self.name,
            "Dt": datetime.strftime(self.invoice_date, '%d/%m/%Y')
            }
        trans_details = {
            "TaxSch": "GST",
            "SupTyp": supply_type,
            "RegRev": "N",
            "EcmGstin": None,
            "IgstOnIntra": "N"
            }
        formated_original = [{
            "transaction": {
                "Version": "1.1",
                "TranDtls": trans_details,
                "DocDtls": doc_details,
                "SellerDtls": seller_details,
                "BuyerDtls": buyer_details,
                "ItemList": item_list,
                "ValDtls": value_details,
                }}]
        headers = {
            "Content-Type": "application/json",
            "X-Cleartax-Auth-Token": access_token,
            "x-cleartax-product": "EInvoice", 
            "gstin": seller_gstin
            }
        data = json.dumps(formated_original)
        # logger.info('-'*75)
        # logger.info(url)
        # logger.info(headers)
        # logger.info(data)
        # logger.info('#'*75)
        req = requests.put(url, data=data, headers=headers, timeout=50)
        content = req.json()
        # logger.info('*'*75)
        # logger.info(content)
        # logger.info('#'*75)
        if isinstance(content, dict) and content.get('error_message', False):
            self.govt_log = content.get('error_message', False)
            return True
        GovtResp = content[0]['govt_response']
        if GovtResp.get('Success', '') == 'Y':
            self.irn_no = GovtResp['Irn']
            self.signed_einvoice = GovtResp.get('SignedInvoice', 'NA')
            self.signed_qrcode = GovtResp.get('SignedQRCode', 'NA')
            
            qr = qrcode.QRCode(
                version=2,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4)
            qr.add_data(self.signed_qrcode)
            qr.make(fit=True)
            img = qr.make_image()
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_image = base64.b64encode(temp.getvalue())
            self.qr_code = qr_image

            self.govt_log = GovtResp.get('Status', 'NA')
            self.irn_ack_no = GovtResp.get('AckNo', 'NA')
            self.irn_ack_date = GovtResp.get('AckDt', 'NA')
            self.irn_success = GovtResp.get('Success', 'NA')

        else:
            self.irn_no = ''
            self.govt_log = GovtResp.get('ErrorDetails', 'Not Applicable')
                
        self.log = content[0]['document_status'] or "Not Applicable"
        return True
    
    def action_make_qr(self):
        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4)
        qr.add_data(self.signed_qrcode)
        qr.make(fit=True)
        img = qr.make_image()
        temp = BytesIO()
        img.save(temp, format="PNG")
        qr_image = base64.b64encode(temp.getvalue())
        self.qr_code = qr_image
        return True
    
    def action_get_irn(self):
        company = self.env['res.company'].browse(1)
        access_token = company.irn_access_token
        seller = self.branch_id.partner_id
        seller_gstin = seller.vat
        headers = {
            "x-cleartax-auth-token": access_token,
            "gstin": seller_gstin,
            }
        logger = logging.getLogger('IRN Update...')
        logger.info('*'*75)
        for invoice in self:
            if invoice.irn_no:
                logger.info('%s'%(invoice.name))
                url = 'https://api.clear.in/einv/v2/eInvoice/get?irn=%s'%(invoice.irn_no)
                req = requests.get(url, headers=headers, timeout=50)
                content = req.json()
                if isinstance(content, list):
                    govt_response = content[0].get('govt_response', False)
                    if isinstance(govt_response, dict):
                        signed_qrcode = govt_response.get('SignedQRCode', False)
                        if signed_qrcode:
                            invoice.signed_qrcode = signed_qrcode
                            invoice.action_make_qr()
            logger.info('-'*75)
        logger.info('#'*75)
        return True
    
    def action_generate_eway_partb(self):
        company = self.env['res.company'].browse(1)
        access_token = company.irn_access_token
        seller = self.branch_id.partner_id
        if not seller.vat:
            raise UserError('Please specify GSTN in Branch')
        seller_gstin = seller.vat
        headers = {
            "x-cleartax-auth-token": access_token,
            "gstin": seller_gstin,
            }
        seller_state_code = seller_gstin[0:2]
        data = {
            "EwbNumber": self.ewb_no,
            "FromPlace": seller.state_id.name,
            "FromState": seller_state_code,
            "ReasonCode": "OTHERS",
            "ReasonRemark": "partb",
            "TransMode": "ROAD",
            "VehicleType": "REGULAR",
            "VehNo": self.vehicle_no
            }
        eway_url = 'https://api.clear.in/einv/v1/ewaybill/update?action=PARTB'
        # logger = logging.getLogger('EWay Update PartB...')
        # logger.info('*'*75)
        # logger.info(headers)
        # logger.info(eway_url)
        # logger.info(data)
        # logger.info('#'*75)
        req = requests.post(eway_url, json=data, headers=headers, timeout=50)
        content = req.json()
        
        if 'UpdatedDate' and 'ValidUpto' in content:
            self.ewb_exp_date = content['ValidUpto']
            self.ewb_update_date = content['UpdatedDate']
            self.ewb_status = 'GENERATED'
        else:
            if 'errors' in content and isinstance(content['errors'], dict):
                if 'error_message' in content['errors']:
                    self.elog = content['errors']['error_message']
        # logger = logging.getLogger('EWay Update PartB...')
        # logger.info('*'*75)
        # logger.info(content)
        # logger.info('#'*75)
        return True
    
    def action_clear_eway(self):
        self.ewb_date = ''
        self.ewb_exp_date = ''
        self.ewb_no = ''
        self.ewb_status = ''
        return True
    
    def action_generate_eway(self, null=None):
        company = self.env['res.company'].browse(1)
        buyer = self.partner_id
        if buyer.l10n_in_gst_treatment == 'overseas':
            buyer_gstin = 'URP'
            buyer_state_code = buyer.vat
        else:
            buyer_gstin = buyer.vat
            if not buyer_gstin:
                raise UserError('Please enter GSTN in Customer')
            buyer_state_code = buyer_gstin[0:2]
        
        seller = self.branch_id.partner_id
        if not seller.vat:
            raise UserError('Please specify GSTN in Branch')
        seller_gstin = seller.vat
        seller_state_code = seller_gstin[0:2]

        transport_date = datetime.strftime(self.invoice_date, '%d/%m/%Y')
        access_token = company.irn_access_token
        if self.move_type == "out_invoice":
            shipping_addr = self.partner_shipping_id
            if not self.trans_mode:
                raise UserError('Select Transport Mode')
            if self.distance <= 0:
                raise UserError('Enter Distance')
            if self.irn_no:
                if not self.trans_mode:
                    raise UserError('Please specify Transport Mode')
                eway_url = company.irn_eway_url
                headers = {
                    "Content-type": "application/json",
                    "x-cleartax-auth-token": access_token,
                    "x-cleartax-product": "EInvoice", 
                    "gstin": seller_gstin
                    }
                shipping_addr_state_code = shipping_addr.vat[0:2]
                ExpShipDtls = {
                    "Addr1": shipping_addr.street or shipping_addr.street or '',
                    "Addr2": shipping_addr.street2 or shipping_addr.street2 or '',
                    "Loc": shipping_addr.street2 or shipping_addr.street2 or '',
                    "Pin": shipping_addr.zip,
                    "Stcd": shipping_addr_state_code
                    }
                if self.trans_mode == "0":
                    if not self.transporter_id:
                        raise UserError('Please specify Transporter Name')
                    if not self.transgst:
                        raise UserError('Please specify Transporter GSTIN')
                    data = [{
                        "Irn": self.irn_no,
                        "TransId": self.transgst,
                        "TransName": self.transporter_id.name,
                        "Distance": self.distance,
                        "ExpShipDtls": ExpShipDtls
                        }]
                elif self.trans_mode == "1":
                    if not self.vehicle_no:
                        raise UserError('Please specify Vehicle No')
                    if not self.vehicle_type:
                        raise UserError('Please specify Vehicle Type')
                    
                    data = [{
                        "Irn": self.irn_no,
                        "TransMode": "1",
                        "TransDocDt": transport_date,
                        "VehNo": self.vehicle_no,
                        "VehType": self.vehicle_type,
                        "Distance": self.distance,
                        "ExpShipDtls": ExpShipDtls
                        }]
                elif self.trans_mode in ("2", "3", "4"):
                    if not self.transportation_doc_date:
                        raise UserError('Please specify Document Date')
                    if not self.transportation_doc_no:
                        raise UserError('Please specify E-waybill Document Number')
                    transport_date = datetime.strftime(self.transportation_doc_date, '%d/%m/%Y')
                    data = [{
                        "Irn": self.irn_no,
                        "TransMode": self.trans_mode,
                        "Distance": self.distance,
                        "ExpShipDtls": ExpShipDtls,
                        "TransDocDt": transport_date,
                        "TransDocNo": self.transportation_doc_no
                        }]
                try:
                    req = requests.post(eway_url, data=json.dumps(data), headers=headers, timeout=50)
                    req.raise_for_status()
                    content = req.json()
                    GovtResp = content[0]['govt_response']
                    if GovtResp.get('Success', '') == 'Y':
                        self.ewb_status = content[0]['ewb_status']
                        self.ewb_no = GovtResp.get('EwbNo', '')
                        
                        ewb_date = GovtResp.get('EwbDt', '')
                        date = ewb_date[:11]
                        day = date[8:10]
                        month = date[5:7]
                        year = date[:4]
                        formatted_ewb_date = '%s/%s/%s '%(day,month,year) + ewb_date[11:]
                        self.ewb_date = formatted_ewb_date
                        
                        ewb_exp_date = GovtResp.get('EwbValidTill', '')
                        if ewb_exp_date:
                            date = ewb_exp_date[:11]
                            day = date[8:10]
                            month = date[5:7]
                            year = date[:4]
                            formatted_ewb_exp_date = '%s/%s/%s '%(day,month,year) + ewb_exp_date[11:]
                            self.ewb_exp_date = formatted_ewb_exp_date
                        
                        self.elog = GovtResp.get('Success', '')
                    else:
                        self.ewb_no = False
                        self.elog = GovtResp.get('ErrorDetails', '')

                except IOError:
                    error_msg = _("Required Fields Missing or Invalid Format For EWAY generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

            if not self.irn_no:
                access_token = company.irn_access_token
                eway_url = company.eway_url
                transport_date = datetime.strftime(self.invoice_date, '%d/%m/%Y')
                headers = {
                    "Content-type": "application/json",
                    "x-cleartax-auth-token": access_token,
                    "x-cleartax-product": "EInvoice", 
                    "gstin": seller_gstin
                    }
                invoice = {
                    "DocumentNumber": self.name,
                    "DocumentType": "OTH",
                    "DocumentDate": transport_date,
                    "SupplyType": "OUTWARD",
                    "SubSupplyType": "OTH",
                    "SubSupplyTypeDesc": "Others",
                    "TransactionType": "Regular",
                    "TransMode": self.trans_mode,
                    "Distance": self.distance,
                    }
                if self.trans_mode == "0":
                    if not self.transporter_id:
                        raise UserError('Please specify Transporter Name')
                    if not self.transgst:
                        raise UserError('Please specify Transporter GSTIN')
                    invoice.update({
                        "TransId": self.transgst,
                        "TransName": self.transporter_id.name,
                        })
                elif self.trans_mode == "1":
                    if not self.vehicle_no:
                        raise UserError('Please specify Vehicle No')
                    if not self.vehicle_type:
                        raise UserError('Please specify Vehicle Type')
                    invoice.update({
                        "TransName": "TRANSPORT",
                        "VehNo": self.vehicle_no,
                        "VehType": self.vehicle_type,
                        })
                elif self.trans_mode in ("2", "3", "4"):
                    if not self.transportation_doc_date:
                        raise UserError('Please specify Document Date')
                    if not self.transportation_doc_no:
                        raise UserError('Please specify E-waybill Document Number')
                    transport_date = datetime.strftime(self.transportation_doc_date, '%d/%m/%Y')
                    invoice.update({
                        "TransName": "TRANSPORT",
                        "TransDocDt": transport_date,
                        "TransDocNo": self.transportation_doc_no
                        })
                item_list = []
                count = 1
                total_untaxed, total_gst, total_igst, total_tcs, total_amount = 0, 0, 0, 0, 0
                dp_dic = {2: 0.01, 3: 0.001}
                dp = dp_dic[buyer.invoice_decimal]
                for line in self.invoice_line_ids:
                    gst_rate, igst_rate, gst_amount, igst_amount, tcs_amount = 0.0, 0.0, 0.0, 0.0, 0.0 
                    taxable_value = line.price_subtotal
                    logger.info('-'*75)
                    logger.info('taxable_value:%s'%taxable_value)
                    for tax in line.tax_ids:
                        group = tax.tax_group_id.name 
                        if group == 'GST':
                            gst_rate = tax.amount
                            gst_amount = round(tools.float_round(taxable_value * gst_rate * 0.01/2, precision_rounding=dp), buyer.invoice_decimal)
                        if group == 'IGST':
                            igst_rate = tax.amount
                            igst_amount = round(tools.float_round(taxable_value * igst_rate * 0.01, precision_rounding=dp), buyer.invoice_decimal)
                        elif group == 'TCS':
                            tcs_base = taxable_value + gst_amount*2 + igst_amount
                            logger.info('tcs_base:%s'%tcs_base)
                            tcs_amount = round(tools.float_round(tcs_base * tax.amount * 0.01, precision_rounding=dp), buyer.invoice_decimal)
                            logger.info('tcs_amount:%s'%tcs_amount)
                    total = line.price_total
                    total = round(tools.float_round(total, precision_rounding=dp), buyer.invoice_decimal)
                    IsServc = "N"
                    if line.product_id.detailed_type == "service":
                        IsServc = "Y"
                    item_dict = {
                        "SlNo": count,
                        "ProdName": line.name,
                        "IsServc": IsServc,
                        "HsnCd": line.product_id.hs_code_id.name,
                        "Qty": line.quantity,
                        "Unit": "NOS",
                        "UnitPrice": line.price_unit,
                        "TotAmt": line.price_subtotal,
                        "Discount": 0,
                        "AssAmt": line.price_subtotal,
                        "CgstRt": gst_rate/2,
                        "SgstRt": gst_rate/2,
                        "IgstRt": igst_rate,
                        "IgstAmt": igst_amount,
                        "CgstAmt": gst_amount,
                        "SgstAmt": gst_amount,
                        "OthChrg": tcs_amount,
                        "TotItemVal": total,
                        }
                    
                    # logger.info(item_dict)
                    # logger.info('#'*75)
                    count = count + 1
                    total_untaxed += taxable_value
                    total_gst += gst_amount
                    total_igst += igst_amount
                    total_tcs += tcs_amount
                    total_amount += total
                    item_list.append(item_dict)
                
                rounding_line = self.line_ids.filtered(lambda l: l.display_type == 'rounding')
                round_off = 0
                if rounding_line:
                    round_off = -1 * rounding_line.balance
                total_tcs = round(tools.float_round(total_tcs, precision_rounding=dp), buyer.invoice_decimal)
                total_amount = round(total_amount + round_off, buyer.invoice_decimal)
                seller_details = {
                    "Gstin": seller_gstin,
                    "LglNm": company.legal_name,
                    "TrdNm": company.trade_name,
                    "Addr1": seller.street,
                    "Loc": seller.state_id.name,
                    "Pin": seller.zip,
                    "Stcd": seller_state_code,
                    }
                buyer_details = {
                    "Gstin": buyer_gstin,
                    "LglNm": buyer.name,
                    "TrdNm": buyer.name,
                    "Pos": buyer_state_code,
                    "Addr1": buyer.street,
                    "Loc": buyer.street2,
                    "Pin": buyer.zip,
                    "Stcd": buyer_state_code,
                    }
                value_details = {
                    "AssVal": total_untaxed,
                    "CgstVal": total_gst,
                    "SgstVal": total_gst,
                    "IgstVal": total_igst,
                    "Discount": 0,
                    "OthChrg": 0,
                    "TotInvVal": total_amount,
                    "TotInvValFc": total_amount,
                    "RndOffAmt": round_off
                    }   
                invoice.update({
                    "BuyerDtls": buyer_details,
                    "SellerDtls": seller_details,
                    "ItemList": item_list,
                    "TotalInvoiceAmount": total_amount,
                    "TotalCgstAmount": total_gst,
                    "TotalSgstAmount": total_gst,
                    "TotalIgstAmount": total_igst,
                    "TotalCessAmount": None,
                    "TotalCessNonAdvolAmount": None,
                    "TotalAssessableAmount": total_untaxed,
                    "OtherAmount": None,
                    "OtherTcsAmount": None,
                    })

                try:
                    req = requests.put(eway_url, data=json.dumps(invoice), headers=headers, timeout=50)
                    req.raise_for_status()
                    content = req.json()
                    GovtResp = content['govt_response']
                    if GovtResp.get('Success', '') == 'Y':
                        self.ewb_status = content['ewb_status']
                        self.ewb_no = GovtResp.get('EwbNo', '')
                        self.ewb_date = GovtResp.get('EwbDt', '')
                        self.ewb_exp_date = GovtResp.get('EwbValidTill', '')
                        self.elog = GovtResp.get('Success', '')
                        self.transaction_id = content['transaction_id']
                    else:
                        self.ewb_no = False
                        self.elog = GovtResp.get('ErrorDetails', '')
                        self.ewb_status = content['ewb_status'] or "Not Applicable"
    
                except IOError:
                    error_msg = _("Required Fields Missing or Invalid Format For EWAY generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    sales_executive_id = fields.Many2one('hr.employee', 'Sales Executive')
    zonal_head_id = fields.Many2one('hr.employee', 'Zonal Head')
    region_id = fields.Many2one('sales.region', 'Region')

    def _select(self):
        return super(AccountInvoiceReport, self)._select() + """,
        move.sales_executive_id,
        move.zonal_head_id,
        move.region_id
        """
