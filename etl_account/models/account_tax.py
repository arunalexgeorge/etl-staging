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

class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    def name_get(self):
        return [(tax.id, '%s (%s)' % (tax.name, tax.type_tax_use)) for tax in self]
    
    def compute_all(self, price_unit, currency=None, quantity=1.0, product=None, partner=None, is_refund=False, handle_price_include=True, include_caba_tags=False, fixed_multiplicator=1):
        if not self:
            company = self.env.company
        else:
            company = self[0].company_id

        # 1) Flatten the taxes.
        taxes, groups_map = self.flatten_taxes_hierarchy(create_map=True)

        # 2) Deal with the rounding methods
        if not currency:
            currency = company.currency_id
        dp_dic = {2: 0.01, 3: 0.001}
        if partner:
            prec = dp_dic[partner.invoice_decimal]
        else:
            prec = currency.rounding
        # In some cases, it is necessary to force/prevent the rounding of the tax and the total
        # amounts. For example, in SO/PO line, we don't want to round the price unit at the
        # precision of the currency.
        # The context key 'round' allows to force the standard behavior.
        round_tax = False if company.tax_calculation_rounding_method == 'round_globally' else True
        if 'round' in self.env.context:
            round_tax = bool(self.env.context['round'])

        if not round_tax:
            prec *= 1e-5

        def recompute_base(base_amount, fixed_amount, percent_amount, division_amount):
            return (base_amount - fixed_amount) / (1.0 + percent_amount / 100.0) * (100 - division_amount) / 100

        base = currency.round(price_unit * quantity)

        # For the computation of move lines, we could have a negative base value.
        # In this case, compute all with positive values and negate them at the end.
        sign = 1
        if currency.is_zero(base):
            sign = -1 if fixed_multiplicator < 0 else 1
        elif base < 0:
            sign = -1
            base = -base

        # Store the totals to reach when using price_include taxes (only the last price included in row)
        total_included_checkpoints = {}
        i = len(taxes) - 1
        store_included_tax_total = True
        # Keep track of the accumulated included fixed/percent amount.
        incl_fixed_amount = incl_percent_amount = incl_division_amount = 0
        # Store the tax amounts we compute while searching for the total_excluded
        cached_tax_amounts = {}
        if handle_price_include:
            for tax in reversed(taxes):
                tax_repartition_lines = (
                    is_refund
                    and tax.refund_repartition_line_ids
                    or tax.invoice_repartition_line_ids
                ).filtered(lambda x: x.repartition_type == "tax")
                sum_repartition_factor = sum(tax_repartition_lines.mapped("factor"))

                if tax.include_base_amount:
                    base = recompute_base(base, incl_fixed_amount, incl_percent_amount, incl_division_amount)
                    incl_fixed_amount = incl_percent_amount = incl_division_amount = 0
                    store_included_tax_total = True
                if tax.price_include or self._context.get('force_price_include'):
                    if tax.amount_type == 'percent':
                        incl_percent_amount += tax.amount * sum_repartition_factor
                    elif tax.amount_type == 'division':
                        incl_division_amount += tax.amount * sum_repartition_factor
                    elif tax.amount_type == 'fixed':
                        incl_fixed_amount += abs(quantity) * tax.amount * sum_repartition_factor * abs(fixed_multiplicator)
                    else:
                        # tax.amount_type == other (python)
                        tax_amount = tax._compute_amount(base, sign * price_unit, quantity, product, partner, fixed_multiplicator) * sum_repartition_factor
                        incl_fixed_amount += tax_amount
                        # Avoid unecessary re-computation
                        cached_tax_amounts[i] = tax_amount
                    # In case of a zero tax, do not store the base amount since the tax amount will
                    # be zero anyway. Group and Python taxes have an amount of zero, so do not take
                    # them into account.
                    if store_included_tax_total and (
                        tax.amount or tax.amount_type not in ("percent", "division", "fixed")
                    ):
                        total_included_checkpoints[i] = base
                        store_included_tax_total = False
                i -= 1

        total_excluded = currency.round(recompute_base(base, incl_fixed_amount, incl_percent_amount, incl_division_amount))
        total_excluded = float_round(total_excluded, precision_rounding=prec)
        # 4) Iterate the taxes in the sequence order to compute missing tax amounts.
        # Start the computation of accumulated amounts at the total_excluded value.
        base = total_included = total_void = total_excluded

        # Flag indicating the checkpoint used in price_include to avoid rounding issue must be skipped since the base
        # amount has changed because we are currently mixing price-included and price-excluded include_base_amount
        # taxes.
        skip_checkpoint = False

        # Get product tags, account.account.tag objects that need to be injected in all
        # the tax_tag_ids of all the move lines created by the compute all for this product.
        product_tag_ids = product.account_tag_ids.ids if product else []

        taxes_vals = []
        i = 0
        cumulated_tax_included_amount = 0
        for tax in taxes:
            price_include = self._context.get('force_price_include', tax.price_include)

            if price_include or tax.is_base_affected:
                tax_base_amount = base
            else:
                tax_base_amount = total_excluded

            tax_repartition_lines = (is_refund and tax.refund_repartition_line_ids or tax.invoice_repartition_line_ids).filtered(lambda x: x.repartition_type == 'tax')
            sum_repartition_factor = sum(tax_repartition_lines.mapped('factor'))

            #compute the tax_amount
            if not skip_checkpoint and price_include and total_included_checkpoints.get(i) is not None and sum_repartition_factor != 0:
                # We know the total to reach for that tax, so we make a substraction to avoid any rounding issues
                tax_amount = total_included_checkpoints[i] - (base + cumulated_tax_included_amount)
                cumulated_tax_included_amount = 0
            else:
                tax_amount = tax.with_context(force_price_include=False)._compute_amount(
                    tax_base_amount, sign * price_unit, quantity, product, partner, fixed_multiplicator)

            # Round the tax_amount multiplied by the computed repartition lines factor.
            tax_amount = float_round(tax_amount, precision_rounding=prec)
            factorized_tax_amount = float_round(tax_amount * sum_repartition_factor, precision_rounding=prec)

            if price_include and total_included_checkpoints.get(i) is None:
                cumulated_tax_included_amount += factorized_tax_amount

            # If the tax affects the base of subsequent taxes, its tax move lines must
            # receive the base tags and tag_ids of these taxes, so that the tax report computes
            # the right total
            subsequent_taxes = self.env['account.tax']
            subsequent_tags = self.env['account.account.tag']
            if tax.include_base_amount:
                subsequent_taxes = taxes[i+1:].filtered('is_base_affected')

                taxes_for_subsequent_tags = subsequent_taxes

                if not include_caba_tags:
                    taxes_for_subsequent_tags = subsequent_taxes.filtered(lambda x: x.tax_exigibility != 'on_payment')

                subsequent_tags = taxes_for_subsequent_tags.get_tax_tags(is_refund, 'base')

            repartition_line_amounts = [float_round(tax_amount * line.factor, precision_rounding=prec) for line in tax_repartition_lines]
            total_rounding_error = float_round(factorized_tax_amount - sum(repartition_line_amounts), precision_rounding=prec)
            nber_rounding_steps = int(abs(total_rounding_error / currency.rounding))
            rounding_error = float_round(nber_rounding_steps and total_rounding_error / nber_rounding_steps or 0.0, precision_rounding=prec)

            for repartition_line, line_amount in zip(tax_repartition_lines, repartition_line_amounts):
                if nber_rounding_steps:
                    line_amount += rounding_error
                    nber_rounding_steps -= 1

                if not include_caba_tags and tax.tax_exigibility == 'on_payment':
                    repartition_line_tags = self.env['account.account.tag']
                else:
                    repartition_line_tags = repartition_line.tag_ids

                taxes_vals.append({
                    'id': tax.id,
                    'name': partner and tax.with_context(lang=partner.lang).name or tax.name,
                    'amount': sign * line_amount,
                    'base': float_round(sign * tax_base_amount, precision_rounding=prec),
                    'sequence': tax.sequence,
                    'account_id': repartition_line._get_aml_target_tax_account().id,
                    'analytic': tax.analytic,
                    'use_in_tax_closing': repartition_line.use_in_tax_closing,
                    'price_include': price_include,
                    'tax_exigibility': tax.tax_exigibility,
                    'tax_repartition_line_id': repartition_line.id,
                    'group': groups_map.get(tax),
                    'tag_ids': (repartition_line_tags + subsequent_tags).ids + product_tag_ids,
                    'tax_ids': subsequent_taxes.ids,
                })

                if not repartition_line.account_id:
                    total_void += line_amount

            # Affect subsequent taxes
            if tax.include_base_amount:
                base += factorized_tax_amount
                if not price_include:
                    skip_checkpoint = True

            total_included += factorized_tax_amount
            i += 1

        base_taxes_for_tags = taxes
        if not include_caba_tags:
            base_taxes_for_tags = base_taxes_for_tags.filtered(lambda x: x.tax_exigibility != 'on_payment')

        base_rep_lines = base_taxes_for_tags.mapped(is_refund and 'refund_repartition_line_ids' or 'invoice_repartition_line_ids').filtered(lambda x: x.repartition_type == 'base')
        total_included = float_round(total_included, precision_rounding=prec)
        return {
            'base_tags': base_rep_lines.tag_ids.ids + product_tag_ids,
            'taxes': taxes_vals,
            'total_excluded': sign * total_excluded,
            'total_included': sign * total_included,
            'total_void': sign * total_void,
            }
        
    @api.model
    def _compute_taxes_for_single_line(self, base_line, handle_price_include=True, include_caba_tags=False, early_pay_discount_computation=None, early_pay_discount_percentage=None):
        
        dp_dic = {2: 0.01, 3: 0.001}
        dp_tools = False
        if base_line and 'partner' in base_line:
            dp = base_line['partner'].invoice_decimal
            dp_tools = dp_dic[dp]
        else:
            dp = 2
            dp_tools = dp_dic[dp]
        orig_price_unit_after_discount = base_line['price_unit'] * (1 - (base_line['discount'] / 100.0))
        price_unit_after_discount = orig_price_unit_after_discount
        taxes = base_line['taxes']._origin
        currency = base_line['currency'] or self.env.company.currency_id
        rate = base_line['rate']

        if early_pay_discount_computation in ('included', 'excluded'):
            remaining_part_to_consider = (100 - early_pay_discount_percentage) / 100.0
            price_unit_after_discount = remaining_part_to_consider * price_unit_after_discount

        if taxes:

            if handle_price_include is None:
                manage_price_include = bool(base_line['handle_price_include'])
            else:
                manage_price_include = handle_price_include

            taxes_res = taxes.with_context(**base_line['extra_context']).compute_all(
                price_unit_after_discount,
                currency=currency,
                quantity=base_line['quantity'],
                product=base_line['product'],
                partner=base_line['partner'],
                is_refund=base_line['is_refund'],
                handle_price_include=manage_price_include,
                include_caba_tags=include_caba_tags,
                )

            to_update_vals = {
                'tax_tag_ids': [Command.set(taxes_res['base_tags'])],
                'price_subtotal': round(tools.float_round(taxes_res['total_excluded'], precision_rounding=dp_tools), dp),
                'price_total': round(tools.float_round(taxes_res['total_included'], precision_rounding=dp_tools), dp),
                }

            if early_pay_discount_computation == 'excluded':
                new_taxes_res = taxes.with_context(**base_line['extra_context']).compute_all(
                    orig_price_unit_after_discount,
                    currency=currency,
                    quantity=base_line['quantity'],
                    product=base_line['product'],
                    partner=base_line['partner'],
                    is_refund=base_line['is_refund'],
                    handle_price_include=manage_price_include,
                    include_caba_tags=include_caba_tags,
                )
                for tax_res, new_taxes_res in zip(taxes_res['taxes'], new_taxes_res['taxes']):
                    new_taxes_res = round(tools.float_round(new_taxes_res['amount'], precision_rounding=dp_tools), dp),
                    tax_res = round(tools.float_round(tax_res['amount'], precision_rounding=dp_tools), dp),
                    delta_tax = new_taxes_res - tax_res
                    delta_tax = round(tools.float_round(delta_tax, precision_rounding=dp_tools), dp),
                    tax_res['amount'] += delta_tax
                    to_update_vals['price_total'] += delta_tax

            tax_values_list = []
            for tax_res in taxes_res['taxes']:
                tax_amount = tax_res['amount'] / rate
                if self.company_id.tax_calculation_rounding_method == 'round_per_line':
                    tax_amount = currency.round(tax_amount)
                tax_amount = round(tools.float_round(tax_amount, precision_rounding=dp_tools), dp)
                tax_rep = self.env['account.tax.repartition.line'].browse(tax_res['tax_repartition_line_id'])
                tax_values_list.append({
                    **tax_res,
                    'tax_repartition_line': tax_rep,
                    'base_amount_currency': tax_res['base'],
                    'base_amount': currency.round(tax_res['base'] / rate),
                    'tax_amount_currency': tax_res['amount'],
                    'tax_amount': tax_amount,
                })

        else:
            price_subtotal = currency.round(price_unit_after_discount * base_line['quantity'])
            to_update_vals = {
                'tax_tag_ids': [Command.clear()],
                'price_subtotal': price_subtotal,
                'price_total': price_subtotal,
                }
            tax_values_list = []

        return to_update_vals, tax_values_list
    
    @api.model
    def _aggregate_taxes(self, to_process, filter_tax_values_to_apply=None, grouping_key_generator=None):

        def default_grouping_key_generator(base_line, tax_values):
            return {'tax': tax_values['tax_repartition_line'].tax_id}

        global_tax_details = {
            'base_amount_currency': 0.0,
            'base_amount': 0.0,
            'tax_amount_currency': 0.0,
            'tax_amount': 0.0,
            'tax_details': defaultdict(lambda: {
                'base_amount_currency': 0.0,
                'base_amount': 0.0,
                'tax_amount_currency': 0.0,
                'tax_amount': 0.0,
                'group_tax_details': [],
                'records': set(),
            }),
            'tax_details_per_record': defaultdict(lambda: {
                'base_amount_currency': 0.0,
                'base_amount': 0.0,
                'tax_amount_currency': 0.0,
                'tax_amount': 0.0,
                'tax_details': defaultdict(lambda: {
                    'base_amount_currency': 0.0,
                    'base_amount': 0.0,
                    'tax_amount_currency': 0.0,
                    'tax_amount': 0.0,
                    'group_tax_details': [],
                    'records': set(),
                }),
            }),
        }
        def add_tax_values(record, results, grouping_key, serialized_grouping_key, tax_values):
            # Add to global results.
            results['tax_amount_currency'] += tax_values['tax_amount_currency']
            results['tax_amount'] += tax_values['tax_amount']

            # Add to tax details.
            if serialized_grouping_key not in results['tax_details']:
                tax_details = results['tax_details'][serialized_grouping_key]
                tax_details.update(grouping_key)
                tax_details['base_amount_currency'] = tax_values['base_amount_currency']
                tax_details['base_amount'] = tax_values['base_amount']
                tax_details['records'].add(record)
            else:
                tax_details = results['tax_details'][serialized_grouping_key]
                if record not in tax_details['records']:
                    tax_details['base_amount_currency'] += tax_values['base_amount_currency']
                    tax_details['base_amount'] += tax_values['base_amount']
                    tax_details['records'].add(record)
            tax_details['tax_amount_currency'] += tax_values['tax_amount_currency']
            tax_details['tax_amount'] += tax_values['tax_amount']
            tax_details['group_tax_details'].append(tax_values)

        grouping_key_generator = grouping_key_generator or default_grouping_key_generator

        for base_line, to_update_vals, tax_values_list in to_process:
            record = base_line['record']

            # Add to global tax amounts.
            global_tax_details['base_amount_currency'] += to_update_vals['price_subtotal']

            currency = base_line['currency'] or self.env.company.currency_id
            base_amount = currency.round(to_update_vals['price_subtotal'] / base_line['rate'])
            global_tax_details['base_amount'] += base_amount

            for tax_values in tax_values_list:
                if filter_tax_values_to_apply and not filter_tax_values_to_apply(base_line, tax_values):
                    continue

                grouping_key = grouping_key_generator(base_line, tax_values)
                serialized_grouping_key = frozendict(grouping_key)

                # Add to invoice line global tax amounts.
                if serialized_grouping_key not in global_tax_details['tax_details_per_record'][record]:
                    record_global_tax_details = global_tax_details['tax_details_per_record'][record]
                    record_global_tax_details['base_amount_currency'] = to_update_vals['price_subtotal']
                    record_global_tax_details['base_amount'] = base_amount
                else:
                    record_global_tax_details = global_tax_details['tax_details_per_record'][record]

                add_tax_values(record, global_tax_details, grouping_key, serialized_grouping_key, tax_values)
                add_tax_values(record, record_global_tax_details, grouping_key, serialized_grouping_key, tax_values)

        return global_tax_details
    
    @api.model
    def _prepare_tax_totals(self, base_lines, currency, tax_lines=None):
        dp_dic = {2: 0.01, 3: 0.001, 0: 0.01}
        dp_tools = False
        if base_lines and 'partner' in base_lines[0]:
            dp = base_lines[0]['partner'].invoice_decimal
            dp_tools = dp_dic[dp]
        else:
            dp = currency.decimal_places
            dp_tools = dp_dic[dp]
        to_process = []
        for base_line in base_lines:
            to_update_vals, tax_values_list = self._compute_taxes_for_single_line(base_line)
            to_process.append((base_line, to_update_vals, tax_values_list))

        def grouping_key_generator(base_line, tax_values):
            source_tax = tax_values['tax_repartition_line'].tax_id
            return {'tax_group': source_tax.tax_group_id}

        global_tax_details = self._aggregate_taxes(to_process, grouping_key_generator=grouping_key_generator)

        tax_group_vals_list = []
        for tax_detail in global_tax_details['tax_details'].values():
            tax_group_vals = {
                'tax_group': tax_detail['tax_group'],
                'base_amount': round(tools.float_round(tax_detail['base_amount_currency'], precision_rounding=dp_tools), dp),
                'tax_amount': round(tools.float_round(tax_detail['tax_amount_currency'], precision_rounding=dp_tools), dp)
                }
            # Handle a manual edition of tax lines.
            if tax_lines is not None:
                matched_tax_lines = [x for x in tax_lines
                    if x['tax_repartition_line'].tax_id.tax_group_id == tax_detail['tax_group']]
                if matched_tax_lines:
                    tax_group_vals_tax_amount = sum(x['tax_amount'] for x in matched_tax_lines)
                    tax_group_vals['tax_amount'] = round(tools.float_round(tax_group_vals_tax_amount, precision_rounding=dp_tools), dp)

            tax_group_vals_list.append(tax_group_vals)

        tax_group_vals_list = sorted(tax_group_vals_list, key=lambda x: (x['tax_group'].sequence, x['tax_group'].id))

        # ==== Partition the tax group values by subtotals ====

        amount_untaxed = global_tax_details['base_amount_currency']
        amount_tax = 0.0

        subtotal_order = {}
        groups_by_subtotal = defaultdict(list)
        for tax_group_vals in tax_group_vals_list:
            tax_group = tax_group_vals['tax_group']
            subtotal_title = tax_group.preceding_subtotal or _("Untaxed Amount")
            sequence = tax_group.sequence

            subtotal_order[subtotal_title] = min(subtotal_order.get(subtotal_title, float('inf')), sequence)
            groups_by_subtotal[subtotal_title].append({
                'group_key': tax_group.id,
                'tax_group_id': tax_group.id,
                'tax_group_name': tax_group.name,
                'tax_group_amount': tax_group_vals['tax_amount'],
                'tax_group_base_amount': tax_group_vals['base_amount'],
                'formatted_tax_group_amount': formatLang(self.env, tax_group_vals['tax_amount'], digits=dp, currency_obj=currency),
                'formatted_tax_group_base_amount': formatLang(self.env, tax_group_vals['base_amount'], digits=dp, currency_obj=currency),
                })
        # ==== Build the final result ====

        subtotals = []
        for subtotal_title in sorted(subtotal_order.keys(), key=lambda k: subtotal_order[k]):
            amount_total = amount_untaxed + amount_tax
            subtotals.append({
                'name': subtotal_title,
                'amount': round(tools.float_round(amount_total, precision_rounding=dp_tools), dp),
                'formatted_amount': formatLang(self.env, amount_total, digits=dp, currency_obj=currency),
                })
            amount_tax += sum(x['tax_group_amount'] for x in groups_by_subtotal[subtotal_title])
        
        amount_untaxed = round(tools.float_round(amount_untaxed, precision_rounding=dp_tools), dp) if dp_tools else amount_untaxed
        amount_tax = tools.float_round(amount_tax, precision_rounding=dp_tools)
        amount_total = amount_untaxed + amount_tax

        display_tax_base = (len(global_tax_details['tax_details']) == 1 and currency.compare_amounts(tax_group_vals_list[0]['base_amount'], amount_untaxed) != 0)\
                           or len(global_tax_details['tax_details']) > 1

        return {
            'amount_untaxed': amount_untaxed,
            'amount_total': tools.float_round(amount_total, precision_rounding=dp_tools) if dp_tools else amount_total,
            'formatted_amount_total': formatLang(self.env, amount_total, digits=dp, currency_obj=currency),
            'formatted_amount_untaxed': formatLang(self.env, amount_untaxed, digits=dp, currency_obj=currency),
            'groups_by_subtotal': groups_by_subtotal,
            'subtotals': subtotals,
            'subtotals_order': sorted(subtotal_order.keys(), key=lambda k: subtotal_order[k]),
            'display_tax_base': display_tax_base
            }