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
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
import logging
logger = logging.getLogger('Reservation..')
from collections import defaultdict
from datetime import timedelta
from operator import itemgetter

from odoo.osv import expression
from odoo.tools.misc import clean_context, OrderedSet, groupby

PROCUREMENT_PRIORITIES = [('0', 'Normal'), ('1', 'Urgent')]

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'
    
    @api.model
    def _run_wkhtmltopdf(self, bodies, report_ref=False, header=None, footer=None,
        landscape=False, specific_paperformat_args=None, set_viewport_size=False):
        if report_ref == 'etl_stock.rm_label_template':
            landscape = True
        return super(IrActionsReport, self)._run_wkhtmltopdf(bodies, report_ref=report_ref, header=header, 
            footer=footer, landscape=landscape, specific_paperformat_args=specific_paperformat_args, 
            set_viewport_size=set_viewport_size)
    
class StockMoves(models.Model):
    _inherit = 'stock.move'
    
    def create_bt_move(self):
        for move in self:
            if self.env.user.id == 2:
                picking = move.picking_id
                branches = self.env['res.branch'].with_context(no_filter=True).search([
                    ('partner_id', '=', picking.partner_id.id)
                    ])
                vendor_branch_id = branches and branches[0].id or False
                if not vendor_branch_id:
                    raise UserError('Branch not linked with this Partner.')
                transit_location_ids = self.env['branch.location'].search([
                    ('branch_id', '=', vendor_branch_id),
                    ('inter_branch_id', '=', self.branch_id.id)
                    ])
                transit_location_id = transit_location_ids and transit_location_ids[0].location_id.id or False
                customer_location_id = self.env['stock.location'].search([('usage', '=', 'customer')])[0].id
                new_moves = []
                if move.quantity_done > 0:
                    new_move = move.with_context(force_date=move.date).create_branch_transit_move(transit_location_id, customer_location_id, vendor_branch_id, picking, move)
                    new_moves.append(new_move)
                for new_move in new_moves:
                    new_move.with_context(force_date=move.date)._action_done()
                    for ac_move in new_move.account_move_ids:
                        ac_move.branch_id = vendor_branch_id
        return True
    
    def create_branch_transit_move(self, transit_location_id, customer_location_id, vendor_branch_id, picking, move):
        move_lines = []
        for move_line in move.move_line_ids:
            move_lines.append((0, 0, {
                'location_id': transit_location_id, 
                'location_dest_id': customer_location_id,
                'lot_id': move_line.lot_id.id,
                'qty_done': move_line.qty_done,
                'branch_id': vendor_branch_id,
                'state': 'draft',
                'picking_id': False,
                'product_id': move_line.product_id.id,
                'product_uom_id': move_line.product_uom_id.id,
                'reference': picking.name,
                'unit_cost': move_line.unit_cost
                }))
        new_move = move.with_context(no_filter=True).create({
            'location_id': transit_location_id, 
            'location_dest_id': customer_location_id,
            'picking_id': False,
            'group_id': False,
            'purchase_line_id': False,
            'branch_id': vendor_branch_id,
            'state': 'confirmed',
            'product_id': move.product_id.id,
            'product_uom': move.product_uom.id,
            'product_uom_qty': move.product_uom_qty,
            'quantity_done': move.quantity_done,
            'name': picking.name,
            'move_line_ids': move_lines,
            'price_unit': move.price_unit,
            'st_branch_id': move.branch_id.id
            })
        return new_move
    
    def _get_price_unit(self):
        self.ensure_one()
        price_unit = self.price_unit
        precision = self.env['decimal.precision'].precision_get('Product Price')
        if self.origin_returned_move_id and self.origin_returned_move_id.sudo().stock_valuation_layer_ids:
            layers = self.origin_returned_move_id.sudo().stock_valuation_layer_ids
            layers |= layers.stock_valuation_layer_ids
            quantity = sum(layers.mapped("quantity"))
            return layers.currency_id.round(sum(layers.mapped("value")) / quantity) if not float_is_zero(quantity, precision_rounding=layers.uom_id.rounding) else 0
        return price_unit if not float_is_zero(price_unit, precision) or self._should_force_price_unit() else self.product_id.standard_price
    
    def create_move_in_svl(self, forced_quantity=None):
        svl_vals_list = self._get_in_svl_vals(forced_quantity)
        if self.stock_valuation_layer_ids:
            for svl in self.stock_valuation_layer_ids:
                svl.delete_svl_am()    
        for svl_val in svl_vals_list:
            svl = self.env['stock.valuation.layer'].create(svl_val)
            svl.correct_svl_jv()
        return True
    
    def _create_in_svl(self, forced_quantity=None):
        svl_vals_list = self._get_in_svl_vals(forced_quantity)
        if svl_vals_list:
            svls = self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
        else:
            return self.env['stock.valuation.layer']
        return svls
    
    def _get_in_move_lines(self):
        self.ensure_one()
        res = OrderedSet()
        for move_line in self.move_line_ids:
            if not move_line.location_id._should_be_valued() and move_line.location_dest_id._should_be_valued():
                res.add(move_line.id)
        return self.env['stock.move.line'].browse(res)
    
    def _get_in_svl_vals(self, forced_quantity):
        svl_vals_list = []
        svl_obj = self.env['stock.valuation.layer']
        for move in self:
            if move.product_id.categ_id.property_valuation != 'real_time':
                continue
            move = move.with_company(move.company_id)
            unit_cost = round(move.price_unit, 3)
            for move_line in move.move_line_ids:
                if move_line.unit_cost:
                    unit_cost = round(move_line.unit_cost, 3)
                valued_quantity = move_line.product_uom_id._compute_quantity(move_line.qty_done, move.product_id.uom_id)
                if unit_cost == 0:
                    domain = [
                        ('product_id', '=', move.product_id.id),
                        ('quantity', '>', 0),
                        ('branch_id', '=', move.branch_id.id),
                        ('create_date', '<=', move.date)
                        ]
                    if move_line.lot_id:
                        domain.append(('lot_id', '=', move_line.lot_id.id))
                    svls = svl_obj.search(domain)
                    total_cost, total_qty = 0.0, 0.0
                    if svls:
                        if len(svls.ids) == 1:
                            unit_cost = round(svls[0].unit_cost, 3)
                        else:
                            for svl in svls:
                                total_cost += abs(svl.value)
                                total_qty += abs(svl.quantity)
                            unit_cost = round(total_cost / total_qty, 3)
                    else:
                        svls = svl_obj.search([
                            ('product_id', '=', move.product_id.id),
                            ('quantity', '>', 0),
                            ('branch_id', '=', move.branch_id.id),
                            ('create_date', '<=', move.date)
                            ])
                        if svls:
                            if len(svls.ids) == 1:
                                unit_cost = round(svls[0].unit_cost, 3)
                            else:
                                for svl in svls:
                                    total_cost += abs(svl.value)
                                    total_qty += abs(svl.quantity)
                                unit_cost = round(total_cost / total_qty, 3)
                    svl = svls and svls[0] or False
                    if unit_cost == 0:
                        unit_cost = move.product_id.standard_price
                    move_line.unit_cost = unit_cost
                        
                unit_cost = round(unit_cost, 3)
                quantity = forced_quantity or valued_quantity
                value = round(unit_cost * quantity, 3)
                svl_vals = {
                    'product_id': move.product_id.id,
                    'value': value,
                    'unit_cost': unit_cost,
                    'quantity': quantity,
                    'move_line_id': move_line.id, 
                    'lot_id': move_line.lot_id.id,
                    'stock_move_id': move.id,
                    'company_id': move.company_id.id,
                    'description': move.reference and '%s - %s' % (move.reference, move.product_id.name) or move.product_id.name,
                    }
                svl_vals_list.append(svl_vals)
        return svl_vals_list
    
    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description):
        self.ensure_one()
        debit_line_vals = {
            'name': description,
            'product_id': self.product_id.id,
            'quantity': qty,
            'product_uom_id': self.product_id.uom_id.id,
            'ref': description,
            'partner_id': partner_id,
            'balance': debit_value,
            'account_id': debit_account_id,
            }
        credit_line_vals = {
            'name': description,
            'product_id': self.product_id.id,
            'quantity': qty,
            'product_uom_id': self.product_id.uom_id.id,
            'ref': description,
            'partner_id': partner_id,
            'balance': -credit_value,
            'account_id': credit_account_id,
            }
        rslt = {'credit_line_vals': credit_line_vals, 'debit_line_vals': debit_line_vals}
        if credit_value != debit_value:
            diff_amount = debit_value - credit_value
            price_diff_account = self.env.context.get('price_diff_account')
            if not price_diff_account:
                raise UserError('Configuration error. Please configure the price difference account on the product or its category to process this operation.')

            rslt['price_diff_line_vals'] = {
                'name': self.name,
                'product_id': self.product_id.id,
                'quantity': qty,
                'product_uom_id': self.product_id.uom_id.id,
                'balance': -diff_amount,
                'ref': description,
                'partner_id': partner_id,
                'account_id': price_diff_account.id,
                }
        return rslt
    
    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, svl_id, description):
        self.ensure_one()
        valuation_partner_id = self._get_partner_id_for_valuation_lines()
        res = [(0, 0, line_vals) for line_vals in self._generate_valuation_lines_data(valuation_partner_id, qty, round(cost, 2), round(cost, 2), debit_account_id, credit_account_id, svl_id, description).values()]
        return res
    
    def _prepare_account_move_vals(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost):
        self.ensure_one()
        valuation_partner_id = self._get_partner_id_for_valuation_lines()
        move_line_ids = self._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, svl_id, description)
        svl = self.env['stock.valuation.layer'].browse(svl_id)
        if self.env.context.get('force_period_date'):
            date = self.env.context.get('force_period_date')
        elif svl.account_move_line_id:
            date = svl.account_move_line_id.date
        else:
            date = fields.Date.context_today(self)
        name = '/'
        if 'move_name' in self._context:
            name = self._context['move_name']
        ob = False
        if 'ob' in self._context:
            ob = True
        return {
            'journal_id': journal_id,
            'line_ids': move_line_ids,
            'partner_id': valuation_partner_id,
            'date': date,
            'ref': description,
            'stock_move_id': self.id,
            'stock_valuation_layer_ids': [(6, None, [svl_id])],
            'move_type': 'entry',
            'is_storno': self.env.context.get('is_returned') and self.env.company.account_storno,
            'branch_id': self.branch_id.id,
            'move_name': name,
            'ob': ob
            }
    
    def _get_accounting_data_for_valuation(self):
        self.ensure_one()
        self = self.with_company(self.company_id)
        accounts_data = self.product_id.product_tmpl_id.get_product_accounts()

        acc_src = self._get_src_account(accounts_data)
        acc_dest = self._get_dest_account(accounts_data)

        acc_valuation = accounts_data.get('stock_valuation', False)
        if acc_valuation:
            acc_valuation = acc_valuation.id
        if not accounts_data.get('stock_journal', False):
            raise UserError('You don\'t have any stock journal defined on your product category, check if you have installed a chart of accounts.')
        if not acc_src:
            raise UserError('Stock Input Account not defined for the product %s on product category %s'%(self.product_id.display_name, self.product_id.categ_id.display_name))
        if not acc_dest:
            raise UserError('Stock Output Account not defined for the product %s on product category %s'%(self.product_id.display_name, self.product_id.categ_id.display_name))
        if not acc_valuation:
            raise UserError('Stock Valuation Account not defined for the product %s on product category %s'%(self.product_id.display_name, self.product_id.categ_id.display_name))
        journal_id = accounts_data['stock_journal'].id
        return journal_id, acc_src, acc_dest, acc_valuation
    
    def _account_entry_move(self, qty, description, svl_id, cost):
        self.ensure_one()
        am_vals = []
        if self.product_id.type != 'product' or self.product_categ_id.property_valuation != 'real_time':
            return am_vals
        if self.restrict_partner_id and self.restrict_partner_id != self.company_id.partner_id:
            return am_vals

        company_from = self._is_out() and self.mapped('move_line_ids.location_id.company_id') or False
        company_to = self._is_in() and self.mapped('move_line_ids.location_dest_id.company_id') or False

        journal_id, acc_src, acc_dest, acc_valuation = self._get_accounting_data_for_valuation()
        # warehouse of the same company, the transit location belongs to this company, so we don't need to create accounting entries
        if self._is_in():
            if self._is_returned(valued_type='in'):
                am_vals.append(self.with_company(company_to).with_context(is_returned=True)._prepare_account_move_vals(acc_dest, acc_valuation, journal_id, qty, description, svl_id, cost))
            else:
                am_vals.append(self.with_company(company_to)._prepare_account_move_vals(acc_src, acc_valuation, journal_id, qty, description, svl_id, cost))

        # Create Journal Entry for products leaving the company
        if self._is_out():
            cost = -1 * cost
            if self._is_returned(valued_type='out'):
                am_vals.append(self.with_company(company_from).with_context(is_returned=True)._prepare_account_move_vals(acc_valuation, acc_src, journal_id, qty, description, svl_id, cost))
            else:
                am_vals.append(self.with_company(company_from)._prepare_account_move_vals(acc_valuation, acc_dest, journal_id, qty, description, svl_id, cost))

        return am_vals
    
    def create_out_svl(self):
        for move in self:
            stock_valuation_layers = self.env['stock.valuation.layer'].sudo()
            stock_valuation_layers |= move._create_out_svl()
            stock_valuation_layers.with_context(force_date=move.date, branch_id=move.branch_id.id)._validate_accounting_entries()
            stock_valuation_layers.correct_to_smldate()
        return True
    
    def _create_out_svl(self, forced_quantity=None):
        svl_vals_list = []
        for move in self:
            if move.product_id.categ_id.property_valuation == 'real_time':
                move = move.with_company(move.company_id).with_context(no_filter=True)
                for move_line in move.move_line_ids:
                    valued_quantity = move_line.product_uom_id._compute_quantity(move_line.qty_done, move.product_id.uom_id)
                    svl_vals = {
                        'quantity': -valued_quantity,
                        'move_line_id': move_line.id,
                        'stock_move_id': move.id,
                        'company_id': move.company_id.id,
                        'product_id': move.product_id.id,
                        'description': move.reference and '%s - %s' % (move.reference, move.product_id.name) or move.product_id.name,
                        }
                    if move_line.lot_id:
                        svl_vals.update({'lot_id': move_line.lot_id.id})
                    svl_vals_list.append(svl_vals)
        return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
    
    def _prepare_common_svl_vals(self):
        return {
            'stock_move_id': self.id,
            'company_id': self.company_id.id,
            'product_id': self.product_id.id,
            'description': self.reference and '%s - %s' % (self.reference, self.product_id.name) or self.product_id.name,
            }
        
    def delete_sm_data(self):
        for sm in self:
            self._cr.execute('delete from stock_move where id=%s'% (sm.id))
        return True

    def _action_assign_base(self, force_qty=False):
        StockMove = self.env['stock.move']
        assigned_moves_ids = OrderedSet()
        partially_available_moves_ids = OrderedSet()
        reserved_availability = {move: move.reserved_availability for move in self}
        roundings = {move: move.product_id.uom_id.rounding for move in self}
        move_line_vals_list = []
        moves_to_redirect = OrderedSet()
        moves_to_assign = self
        if not force_qty:
            moves_to_assign = self.filtered(lambda m: m.state in ['confirmed', 'waiting', 'partially_available'])
        for move in moves_to_assign:
            rounding = roundings[move]
            if not force_qty:
                missing_reserved_uom_quantity = move.product_uom_qty
            else:
                missing_reserved_uom_quantity = force_qty
            missing_reserved_uom_quantity -= reserved_availability[move]
            missing_reserved_quantity = move.product_uom._compute_quantity(missing_reserved_uom_quantity, move.product_id.uom_id, rounding_method='HALF-UP')
            if move._should_bypass_reservation():
                if move.move_orig_ids:
                    available_move_lines = move._get_available_move_lines(assigned_moves_ids, partially_available_moves_ids)
                    for (location_id, lot_id, package_id, owner_id), quantity in available_move_lines.items():
                        qty_added = min(missing_reserved_quantity, quantity)
                        move_line_vals = move._prepare_move_line_vals(qty_added)
                        move_line_vals.update({
                            'location_id': location_id.id,
                            'lot_id': lot_id.id,
                            'lot_name': lot_id.name,
                            'owner_id': owner_id.id,
                            })
                        move_line_vals_list.append(move_line_vals)
                        missing_reserved_quantity -= qty_added
                        if float_is_zero(missing_reserved_quantity, precision_rounding=move.product_id.uom_id.rounding):
                            break

                if missing_reserved_quantity and move.product_id.tracking == 'serial' and (move.picking_type_id.use_create_lots or move.picking_type_id.use_existing_lots):
                    for i in range(0, int(missing_reserved_quantity)):
                        move_line_vals_list.append(move._prepare_move_line_vals(quantity=1))
                elif missing_reserved_quantity:
                    to_update = move.move_line_ids.filtered(lambda ml: ml.product_uom_id == move.product_uom and
                        ml.location_id == move.location_id and
                        ml.location_dest_id == move.location_dest_id and
                        ml.picking_id == move.picking_id and
                        not ml.lot_id and
                        not ml.package_id and
                        not ml.owner_id)
                    if to_update:
                        to_update[0].reserved_uom_qty += move.product_id.uom_id._compute_quantity(
                            missing_reserved_quantity, move.product_uom, rounding_method='HALF-UP')
                    else:
                        move_line_vals_list.append(move._prepare_move_line_vals(quantity=missing_reserved_quantity))
                assigned_moves_ids.add(move.id)
                moves_to_redirect.add(move.id)
            else:
                if float_is_zero(move.product_uom_qty, precision_rounding=move.product_uom.rounding):
                    assigned_moves_ids.add(move.id)
                elif not move.move_orig_ids:
                    if move.procure_method == 'make_to_order':
                        continue
                    # If we don't need any quantity, consider the move assigned.
                    need = missing_reserved_quantity
                    if float_is_zero(need, precision_rounding=rounding):
                        assigned_moves_ids.add(move.id)
                        continue
                    # Reserve new quants and create move lines accordingly.
                    forced_package_id = move.package_level_id.package_id or None
                    available_quantity = move._get_available_quantity(move.location_id, package_id=forced_package_id)
                    if available_quantity <= 0:
                        continue
                    taken_quantity = move._update_reserved_quantity(need, available_quantity, move.location_id, package_id=forced_package_id, strict=False)
                    if float_is_zero(taken_quantity, precision_rounding=rounding):
                        continue
                    moves_to_redirect.add(move.id)
                    if float_compare(need, taken_quantity, precision_rounding=rounding) == 0:
                        assigned_moves_ids.add(move.id)
                    else:
                        partially_available_moves_ids.add(move.id)
                else:
                    available_move_lines = move._get_available_move_lines(assigned_moves_ids, partially_available_moves_ids)
                    if not available_move_lines:
                        continue
                    for move_line in move.move_line_ids.filtered(lambda m: m.reserved_qty):
                        if available_move_lines.get((move_line.location_id, move_line.lot_id, move_line.result_package_id, move_line.owner_id)):
                            available_move_lines[(move_line.location_id, move_line.lot_id, move_line.result_package_id, move_line.owner_id)] -= move_line.reserved_qty
                    for (location_id, lot_id, package_id, owner_id), quantity in available_move_lines.items():
                        need = move.product_qty - sum(move.move_line_ids.mapped('reserved_qty'))
                        available_quantity = move._get_available_quantity(location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)
                        if float_is_zero(available_quantity, precision_rounding=rounding):
                            continue
                        taken_quantity = move._update_reserved_quantity(need, min(quantity, available_quantity), location_id, lot_id, package_id, owner_id)
                        if float_is_zero(taken_quantity, precision_rounding=rounding):
                            continue
                        moves_to_redirect.add(move.id)
                        if float_is_zero(need - taken_quantity, precision_rounding=rounding):
                            assigned_moves_ids.add(move.id)
                            break
                        partially_available_moves_ids.add(move.id)
            if move.product_id.tracking == 'serial':
                move.next_serial_count = move.product_uom_qty

        self.env['stock.move.line'].create(move_line_vals_list)
        StockMove.browse(partially_available_moves_ids).write({'state': 'partially_available'})
        StockMove.browse(assigned_moves_ids).write({'state': 'assigned'})
        if not self.env.context.get('bypass_entire_pack'):
            self.mapped('picking_id')._check_entire_pack()
        
    def _action_assign(self, force_qty=False):
        if 'normal_assign' in self._context:
            return self._action_assign_base(force_qty=force_qty)
        elif 'mrp_assign' in self._context or 'sfgrm_assign' in self._context:
            move_line_obj = self.env['stock.move.line']
            logger.info('*'*75)
            for move in self:
                move.move_line_ids.unlink()
                available_quantity = move._get_available_quantity(move.location_id)
                if available_quantity <= 0:
                    continue
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', move.location_id.id),
                    ])
                move_qty = move.product_uom_qty
                reserved_qty = 0
                remaining_qty = move_qty
                for quant in quants:
                    available_qty = quant.available_quantity
                    logger.info('available_qty:',available_qty)
                    if available_qty > 0 and remaining_qty > 0:
                        move_line_vals = move._prepare_move_line_vals()
                        if remaining_qty <= available_qty:
                            reserved_qty += remaining_qty
                            qty = remaining_qty
                            remaining_qty = 0
                        else:
                            reserved_qty += available_qty
                            remaining_qty = remaining_qty - reserved_qty
                            qty = available_qty
                        logger.info('reserved_qty:',reserved_qty)
                        if reserved_qty > 0:
                            move_line_vals.update({
                                'reserved_uom_qty': qty,
                                'lot_id': quant.lot_id.id
                                })
                            if move.raw_material_production_id:
                                move_line_vals.update({
                                    'production_id': move.raw_material_production_id.id,
                                    'workorder_id': move.workorder_id.id
                                    })
                            move_line_obj.create(move_line_vals)
                        logger.info('remaining_qty:',remaining_qty)
                        if remaining_qty == 0:
                            break
                logger.info('#'*75)
                if remaining_qty == 0:
                    move.write({'state': 'assigned'})
                elif remaining_qty > 0:
                    move.write({'state': 'partially_available'})
            return True
        else:
            return self._action_assign_base(force_qty=force_qty)
            
    def _compute_dn(self):
        for move in self:
            picking_delivery = False
            if move.picking_type_id:
                if move.picking_type_id.code == 'outgoing':
                    picking_delivery = True
                elif move.picking_type_id.code == 'incoming' and move.location_id.usage == 'customer':
                    picking_delivery = True
            move.picking_delivery = picking_delivery
    
    def _login_user(self):
        for move in self:
            move.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    @api.depends('quantity_done', 'price_unit')
    def _compute_total_cost(self):
        for move in self:
            total_cost = move.quantity_done * move.price_unit
            move.total_cost = round(tools.float_round(total_cost, precision_rounding=0.01), 2)
            
    picking_delivery = fields.Boolean('Picking Delivery', compute='_compute_dn')
    serial_line_ids = fields.One2many('picking.serial.line', 'move_id', 'Serial Numbers')
    branch_transit_created = fields.Boolean('Branch Transit Created', copy=False)
    sequence = fields.Integer("Sequence", default=1)
    sl_no = fields.Integer("SL No.", compute='_compute_sl_no', store=True)
    product_categ_id = fields.Many2one('product.category', compute='_compute_product_category', store=True)
    category_type = fields.Selection([
        ('rm', 'RM'), 
        ('sfg', 'SFG'), 
        ('fg', 'FG'),
        ('scrap', 'Scrap'),
        ('service', 'Service'),
        ('none', 'None')
        ], string='Category Type', 
        compute='_compute_product_category', store=True)
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    price_unit = fields.Float('Unit Cost', digits=(16,3))
    total_cost = fields.Float('Total Cost', compute='_compute_total_cost', store=True, digits=(16,2))
    st_branch_id = fields.Integer('ST Branch ID')
    
    @api.depends('product_id', 'product_id.categ_id', 'product_id.categ_id.category_type')
    def _compute_product_category(self):
        for quant in self:
            quant.product_categ_id = quant.product_id.categ_id.id
            if quant.product_id.categ_id.category_type:
                category_type = quant.product_id.categ_id.category_type
            else:
                category_type = 'none'
            quant.category_type = category_type
    
    def action_print_rm_label(self):
        return self.env.ref('etl_stock.action_rm_label').with_context(landscape=True).report_action(self)
    
    def get_lot_numbers(self):
        lot_numbers = ', '.join(line.lot_id.name for line in self.move_line_ids)
        return lot_numbers
    
    @api.depends('sequence')
    def _compute_sl_no(self):
        for line in self:
            line.sl_no = line.sequence
            
    def _split(self, qty, restrict_partner_id=False):
        old_list = super(StockMoves, self)._split(qty, restrict_partner_id=restrict_partner_id)
        new_list = []
        for val in old_list:
            if 'alt_uom_qty' in val and 'alt_uom_qty_actual' in val:
                val['alt_uom_qty'] = val['alt_uom_qty'] - val['alt_uom_qty_actual']
                val['alt_uom_qty_actual'] = 0
                val['qc_id'] = False
                val['qc_status'] = 'pending'
            new_list.append(val)
        self.alt_uom_qty = self.alt_uom_qty_actual
        return new_list

class StockMoveLines(models.Model):
    _inherit = 'stock.move.line'
    
    @api.constrains('qty_done')
    def _check_positive_qty_done(self):
        for ml in self:
            if ml.qty_done < 0:
                print(ml.id)
                raise ValidationError('You can not enter negative quantities : %s'%(ml.product_id.name_get()[0][1]))
        
    @api.depends('state', 'location_id', 'location_id.usage', 'location_dest_id', 'location_dest_id.usage')
    def _compute_im(self):
        for sml in self:
            if sml.location_id and sml.location_id.usage == 'internal' and sml.location_dest_id and sml.location_dest_id.usage == 'internal':
                sml.it_ok = True
            else:
                sml.it_ok = False
        
    unit_cost = fields.Float('Unit Cost', digits=(16, 3))
    it_ok = fields.Boolean('IT', compute='_compute_im', store=True)
    
    def name_get(self):
        return [(sml.id, '%s %s' % (sml.id, sml.reference and ' ['+sml.reference+']' or sml.product_id.default_code)) for sml in self]
    
    @api.model
    def _create_correction_svl(self, move, diff):
        return True
        
    def delete_sml_data(self):
        for sml in self:
            self._cr.execute('delete from stock_move_line where id=%s'% (sml.id))
        return True
    
    @api.constrains('reserved_uom_qty')
    def _check_reserved_done_quantity(self):
        for move_line in self:
            if move_line.state == 'done' and not float_is_zero(move_line.reserved_uom_qty, precision_digits=self.env['decimal.precision'].precision_get('Product Unit of Measure')):
                move_line.reserved_uom_qty = 0
                # raise ValidationError(_('A done move line should never have a reserved quantity.'))
    