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
from odoo.tools.float_utils import float_compare, float_is_zero
from odoo.tools.misc import clean_context, OrderedSet, groupby
from asyncio.base_events import ssl
import logging
logger = logging.getLogger(__name__)
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime
from collections import defaultdict
from odoo.fields import Command

class Picking(models.Model):
    _inherit = 'stock.picking'
    
    def action_confirm(self):
        res = super(Picking, self).action_confirm()
        for picking in self:
            picking.state = 'confirmed'
        return res
    
    def clear_reservation_warning(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                pass
        return True
    
    def update_done_quantity(self):
        psl_obj = self.env['picking.serial.line']
        for picking in self:
            if picking.serial_line_ids:
                for move in picking.move_ids_without_package:
                    move_qty, move_reserved_qty = 0.0, 0.0
                    if move.alt_uom_id: 
                        for move_line in move.move_line_ids:
                            psls = psl_obj.search([
                                ('product_id', '=', move.product_id.id),
                                ('alt_uom_id', '=', move.alt_uom_id.id),
                                ('picking_id', '=', picking.id),
                                ('lot_id', '=', move_line.lot_id.id)
                                ])
                            qty_reserved = sum([round(psl.quantity, 3) for psl in psls if picking.state not in ('cancel', 'done', 'draft')])
                            qty_done = sum([round(psl.quantity, 3) for psl in psls if psl.scanned])
                            move_line.reserved_uom_qty = qty_reserved
                            move_line.qty_done = qty_done
                            move_qty += qty_done
                        move.quantity_done = move_qty
        return True
    
    def update_done_qty(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                if move.state == 'done':
                    done_qty = 0.0
                    for line in move.move_line_ids:
                        done_qty += line.qty_done
                    move.quantity_done = done_qty
                move.sale_line_id.write({'recompute': not move.sale_line_id.recompute})
        return True
    
    def _compute_picking_out(self):
        for picking in self:
            picking_delivery = False
            if picking.picking_type_id:
                if picking.picking_type_id.code in ('outgoing', 'internal'):
                    picking_delivery = True
                elif picking.picking_type_id.code == 'incoming' and picking.location_id.usage == 'customer':
                    picking_delivery = True
            picking.picking_delivery = picking_delivery
    
    def _compute_picking_inbranch(self):
        for picking in self:
            picking_inbranch = False
            if picking.picking_type_id:
                if picking.picking_type_id.code == 'incoming' and picking.partner_id.is_branch:
                    picking_inbranch = True
            picking.picking_inbranch = picking_inbranch
            
    @api.depends('picking_type_id', 'partner_id')
    def _compute_location_id(self):
        for picking in self:
            picking = picking.with_company(picking.company_id)
            if picking.picking_type_id and picking.state == 'draft':
                if picking.picking_type_id.default_location_src_id:
                    location_id = picking.picking_type_id.default_location_src_id.id
                elif picking.partner_id:
                    location_id = picking.partner_id.property_stock_supplier.id
                else:
                    _customerloc, location_id = self.env['stock.warehouse']._get_partner_locations()

                if picking.picking_type_id.default_location_dest_id:
                    location_dest_id = picking.picking_type_id.default_location_dest_id.id
                elif picking.partner_id:
                    location_dest_id = picking.partner_id.property_stock_customer.id
                else:
                    location_dest_id, _supplierloc = self.env['stock.warehouse']._get_partner_locations()

                picking.location_id = location_id
                picking.location_dest_id = location_dest_id
    
    def _compute_so_details(self):
        for picking in self:
            sale_order_id, so_type = False, 'none'
            if picking.picking_type_id.code == 'outgoing':
                orders = self.env['sale.order'].search([('name', '=', picking.origin)], limit=1)
                if orders:
                    sale_order_id = orders[0].id
                    so_type = orders[0].so_type
            picking.sale_order_id = sale_order_id
            picking.so_type = so_type
    
    def _compute_po_details(self):
        for picking in self:
            purchase_order_id, po_type = False, 'none'
            if picking.picking_type_id.code == 'incoming':
                orders = self.env['purchase.order'].search([('name', '=', picking.origin)], limit=1)
                if orders:
                    purchase_order_id = orders[0].id
                    po_type = orders[0].po_type
            picking.purchase_order_id = purchase_order_id
            picking.po_type = po_type
    
    def _check_bt(self):
        for picking in self:
            if picking.partner_id and picking.partner_id.is_branch:
                picking.branch_tranfser = True
            else:
                picking.branch_tranfser = False
                
    @api.depends('immediate_transfer', 'state')
    def _compute_show_check_availability(self):
        """ According to `picking.show_check_availability`, the "check availability" button will be
        displayed in the form view of a picking.
        """
        for picking in self:
            if picking.immediate_transfer or picking.state not in ('confirmed', 'waiting', 'assigned') or picking.picking_type_id.code == 'incoming':
                picking.show_check_availability = False
                continue
            picking.show_check_availability = any(
                move.state in ('waiting', 'confirmed', 'partially_available') and
                float_compare(move.product_uom_qty, 0, precision_rounding=move.product_uom.rounding)
                for move in picking.move_ids)
    
    def _compute_sn(self):
        for picking in self:
            picking.sn_list = ','.join(line.serial_id and line.serial_id.name.replace('\n', '') or '' for line in picking.serial_line_ids)
            picking.scanned_list = ','.join(line.serial_id and line.serial_id.name.replace('\n', '') or '' for line in picking.serial_line_ids if line.scanned)
            picking.scanned_list_count = len([line.name for line in picking.serial_line_ids if line.scanned])
            picking.sn_list_count = len([line.name for line in picking.serial_line_ids])
    
    def _compute_picking_slip_data(self):
        for picking in self:
            pctr_bag, pctr_belt, pctr_weight = 0, 0, 0
            bg_box, bg_bag, bg_roll, bg_weight = 0, 0, 0, 0
            bvc_drum, bvc_can, bvc_ltr, bvc_weight = 0, 0, 0, 0
            ct_bag, ct_belt, ct_weight = 0, 0, 0
            if picking.serial_line_ids:
                for serial in picking.serial_line_ids:
                    if serial.alt_uom_id:
                        uom = serial.alt_uom_id.name
                        fg_type = serial.product_id.categ_id.fg_type 
                        if fg_type == 'pctr':
                            pctr_weight += serial.quantity
                            if uom == 'BAG': 
                                pctr_bag += 1
                            elif uom == 'BELTS': 
                                pctr_belt += round(serial.quantity/serial.product_id.weight_belt, 0)
                        elif fg_type == 'bg':
                            bg_weight += serial.quantity
                            if uom == 'BOX': 
                                bg_box += 1
                            elif uom == 'BAG': 
                                bg_bag += 1
                            elif uom == 'ROLL': 
                                bg_roll += round(serial.quantity/serial.product_id.weight_belt, 0)
                        elif fg_type == 'bvc':
                            bvc_weight += serial.quantity
                            if uom == 'DRUM': 
                                bvc_drum += 1
                            if uom == 'CAN': 
                                bvc_can += 1
                        elif fg_type == 'ct':
                            ct_weight += serial.quantity
                            if uom == 'BAG': 
                                ct_bag += 1
                            elif uom == 'BELTS': 
                                ct_belt += round(serial.quantity/serial.product_id.weight_belt, 0)
                            
            picking.pctr_bag = round(pctr_bag, 3)
            picking.pctr_belt = round(pctr_belt, 3)
            picking.pctr_weight = round(pctr_weight, 3)
            
            picking.bg_box = round(bg_box, 3)
            picking.bg_bag = round(bg_bag, 3)
            picking.bg_roll = round(bg_roll, 3)
            picking.bg_weight = round(bg_weight, 3)
            
            picking.bvc_drum = round(bvc_drum, 3)
            picking.bvc_can = round(bvc_can, 3)
            picking.bvc_ltr = round(bvc_ltr, 3)
            picking.bvc_weight = round(bvc_weight, 3)
            
            picking.ct_bag = round(ct_bag, 3)
            picking.ct_belt = round(ct_belt, 3)
            picking.ct_weight = round(ct_weight, 3)
    
    @api.depends('show_validate', 'immediate_transfer', 'move_ids.reserved_availability', 'move_ids.quantity_done')
    def _compute_show_qty_button(self):
        self.show_set_qty_button = False
        self.show_clear_qty_button = False
        for picking in self:
            if picking.state not in ('done', 'cancel'):
                self.show_set_qty_button = True
            else:
                if not picking.show_validate or picking.immediate_transfer:
                    continue
                if any(float_is_zero(m.quantity_done, precision_rounding=m.product_uom.rounding) and not float_is_zero(m.reserved_availability, precision_rounding=m.product_uom.rounding) for m in picking.move_ids):
                    picking.show_set_qty_button = True
                elif any(not float_is_zero(m.quantity_done, precision_rounding=m.product_uom.rounding) and float_compare(m.quantity_done, m.reserved_availability, precision_rounding=m.product_uom.rounding) == 0 for m in picking.move_ids):
                    picking.show_clear_qty_button = True
    
    def product_details(self, serial_details, s):
        prod_lot = s.split('_')
        product_id = int(prod_lot[0])
        product = self.env['product.product'].browse(product_id)
        return [product.default_code, product.name, product.product_group2_id.name,
            serial_details[s]['bag'], serial_details[s]['belt'], serial_details[s]['weight'],
            prod_lot[1], serial_details[s]['s_list']]
    
    def total_sn_bag(self):
        return round(self.pctr_bag + self.bg_bag + self.ct_bag, 3) 
    
    def total_sn_weight(self):
        return round(self.pctr_weight + self.bg_weight + self.bvc_weight + self.ct_weight, 3)
    
    def get_serial_details(self):
        sl_dic = {}
        product_dic = {}
        total_bag, total_belt, total_weight = 0, 0, 0
        for sl in self.serial_line_ids:
            product_lot = '%s_%s'%(str(sl.product_id.id), sl.lot_id.name)
            if not product_lot in product_dic:
                product_dic.update({product_lot: sl.product_id})
            if sl.alt_uom_id.type == 'base':
                belt = sl.product_id.belt_no
                bag = 1
            else:
                belt = int(sl.quantity / sl.product_id.weight_belt)
                bag = 0
            weight = round(sl.quantity, 3)
            total_bag += bag
            total_belt += belt
            total_weight += weight
            if product_lot in sl_dic:
                s_list = sl_dic[product_lot]['s_list']
                s_list.append(sl.serial_id.name)
                sl_dic.update({product_lot: {
                    'bag': bag + sl_dic[product_lot]['bag'],
                    'belt': belt + sl_dic[product_lot]['belt'],
                    'weight': round(weight + sl_dic[product_lot]['weight'], 3),
                    's_list': s_list
                    }})
            else:
                sl_dic.update({product_lot: {
                    'bag': bag,
                    'belt': belt,
                    'weight': weight,
                    's_list': [sl.serial_id.name]
                    }})
        return [sl_dic, round(total_weight, 3), total_bag]

    transport_mode = fields.Char('Transportation Mode')
    transport_company = fields.Char('Transport Company')
    vehicle_no = fields.Char('Vehicle No')
    dispatch_date = fields.Date('Dispatch Date')
    show_set_qty_button = fields.Boolean(compute='_compute_show_qty_button')
    show_clear_qty_button = fields.Boolean(compute='_compute_show_qty_button')
    show_check_availability = fields.Boolean(
        compute='_compute_show_check_availability',
        help='Technical field used to compute whether the button "Check Availability" should be displayed.')
    serial_number = fields.Char('Serial Number')
    picking_delivery = fields.Boolean('Picking Out', compute='_compute_picking_out')
    picking_inbranch = fields.Boolean('Picking In Branch', compute='_compute_picking_inbranch')
    location_id = fields.Many2one(
        'stock.location', "Source Location",
        compute="_compute_location_id", store=True, precompute=True, readonly=False,
        check_company=True, required=True,
        states={'done': [('readonly', True)]})
    location_dest_id = fields.Many2one(
        'stock.location', "Destination Location",
        compute="_compute_location_id", store=True, precompute=True, readonly=False,
        check_company=True, required=True,
        states={'done': [('readonly', True)]})
    scanned_list = fields.Text('SN Scanned List', compute='_compute_sn')
    sn_list = fields.Text('SN List', compute='_compute_sn')
    scanned_list_count = fields.Integer('Scanned SN', compute='_compute_sn')
    sn_list_count = fields.Integer('Total SN', compute='_compute_sn')
    branch_return = fields.Boolean('Branch Return')
    
    pctr_bag = fields.Integer(compute='_compute_picking_slip_data')
    pctr_belt = fields.Integer(compute='_compute_picking_slip_data')
    pctr_weight = fields.Float(compute='_compute_picking_slip_data', digits=(16,3))
    
    bg_box = fields.Integer(compute='_compute_picking_slip_data')
    bg_bag = fields.Integer(compute='_compute_picking_slip_data')
    bg_roll = fields.Integer(compute='_compute_picking_slip_data')
    bg_weight = fields.Float(compute='_compute_picking_slip_data', digits=(16,3))
    
    bvc_drum = fields.Integer(compute='_compute_picking_slip_data')
    bvc_can = fields.Integer(compute='_compute_picking_slip_data')
    bvc_ltr = fields.Integer(compute='_compute_picking_slip_data')
    bvc_weight = fields.Float(compute='_compute_picking_slip_data')
    
    ct_bag = fields.Integer(compute='_compute_picking_slip_data')
    ct_belt = fields.Integer(compute='_compute_picking_slip_data')
    ct_weight = fields.Float(compute='_compute_picking_slip_data', digits=(16,3))
    remarks = fields.Char('Remarks')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Another Operation'),
        ('confirmed', 'Waiting'),
        ('assigned', 'Ready'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
        ], string='Status', compute='_compute_state',
        copy=False, index=True, readonly=True, store=True, tracking=True,)
    sale_order_id = fields.Many2one('sale.order', 'Sale Order', compute='_compute_so_details')
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
        ], 'Sales Order Type', compute='_compute_so_details')
    purchase_order_id = fields.Many2one('purchase.order', 'Purchase Order', compute='_compute_po_details')
    po_type = fields.Selection([
        ('service', 'Engineering Purchase'),
        ('service_po', 'Service Purchase'),
        ('stock', 'Stock Transfer Purchase'),
        ('internal', 'Internal Transfer'),
        ('import', 'Import Purchase'),
        ('domestic', 'Domestic Purchase'),
        ('sub_con', 'Subcon Purchase'),
        ('packing', 'Packing Material Purchase'),
        ('none', 'None')
        ], 'Purchase Order Type', compute='_compute_po_details')
    
    invoiced = fields.Boolean('Invoiced', copy=False)
    sale_invoice_id = fields.Many2one('account.move', 'Sales Invoice', copy=False)
    billed = fields.Boolean('Billed', copy=False)
    purchase_bill_id = fields.Many2one('account.move', 'Purchase Bill', copy=False)
    dn_ref = fields.Char('DN/GRN Reference', copy=False)
    branch_tranfser = fields.Boolean('Branch Transfer', compute='_check_bt')
    branch_received = fields.Boolean('Received In Branch', copy=False)
    
    @api.depends('move_type', 'immediate_transfer', 'move_ids.state', 'move_ids.picking_id')
    def _compute_state(self):
        picking_moves_state_map = defaultdict(dict)
        picking_move_lines = defaultdict(set)
        for move in self.env['stock.move'].search([('picking_id', 'in', self.ids)]):
            picking_id = move.picking_id
            move_state = move.state
            picking_moves_state_map[picking_id.id].update({
                'any_draft': picking_moves_state_map[picking_id.id].get('any_draft', False) or move_state == 'draft',
                'all_cancel': picking_moves_state_map[picking_id.id].get('all_cancel', True) and move_state == 'cancel',
                'all_cancel_done': picking_moves_state_map[picking_id.id].get('all_cancel_done', True) and move_state in ('cancel', 'done'),
                'all_done_are_scrapped': picking_moves_state_map[picking_id.id].get('all_done_are_scrapped', True) and (move.scrapped if move_state == 'done' else True),
                'any_cancel_and_not_scrapped': picking_moves_state_map[picking_id.id].get('any_cancel_and_not_scrapped', False) or (move_state == 'cancel' and not move.scrapped),
            })
            picking_move_lines[picking_id.id].add(move.id)
        for picking in self:
            picking_id = (picking.ids and picking.ids[0]) or picking.id
            if not picking_moves_state_map[picking_id]:
                picking.state = 'draft'
            elif picking_moves_state_map[picking_id]['any_draft']:
                picking.state = 'draft'
            elif picking_moves_state_map[picking_id]['all_cancel']:
                picking.state = 'cancel'
            elif picking_moves_state_map[picking_id]['all_cancel_done']:
                if picking_moves_state_map[picking_id]['all_done_are_scrapped'] and picking_moves_state_map[picking_id]['any_cancel_and_not_scrapped']:
                    picking.state = 'cancel'
                else:
                    picking.state = 'done'
            else:
                relevant_move_state = self.env['stock.move'].browse(picking_move_lines[picking_id])._get_relevant_state_among_moves()
                if picking.immediate_transfer and relevant_move_state not in ('draft', 'cancel', 'done'):
                    picking.state = 'assigned'
                elif relevant_move_state == 'partially_available':
                    picking.state = 'assigned'
                else:
                    picking.state = relevant_move_state
                    
    def _login_user(self):
        for lot in self:
            lot.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    def create_st_invoice(self):
        invoice_item_sequence = 0
        for picking in self:
            order = picking.sale_order_id
            invoice_vals = order._prepare_invoice()
            invoice_line_vals = []
            for move in picking.move_ids_without_package:
                if move.alt_uom_qty_actual > 0 and move.quantity_done > 0:
                    line_vals = move.sale_line_id._prepare_invoice_line(sequence=invoice_item_sequence)
                    line_vals.update({
                        'price_unit': move.price_unit,
                        'quantity': move.quantity_done,
                        'alt_uom_id': move.alt_uom_id and move.alt_uom_id.id or False,
                        'alt_uom_qty': move.alt_uom_qty_actual,
                        'sequence': move.sequence
                        })
                    invoice_line_vals.append(Command.create(line_vals))
                    invoice_item_sequence += 1

            invoice_vals['invoice_line_ids'] += invoice_line_vals

            move = self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals)
            move.message_post_with_view(
                'mail.message_origin_link',
                values={'self': move, 'origin': move.line_ids.sale_line_ids.order_id},
                subtype_id=self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note'))
            picking.invoiced = True
            picking.sale_invoice_id = move.id
        return self.action_view_invoice()
    
    def action_view_invoice(self):
        if self.sale_invoice_id:
            action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
            form_view = [(self.env.ref('account.view_move_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = self.sale_invoice_id.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action
    
    def create_st_bill(self):
        for picking in self:
            order = picking.purchase_order_id
            invoice_vals = order._prepare_invoice()
            for move in picking.move_ids_without_package:
                line_vals = move.purchase_line_id._prepare_account_move_line()
                line_vals.update({
                    'price_unit': move.price_unit,
                    'quantity': move.quantity_done,
                    'alt_uom_id': move.alt_uom_id and move.alt_uom_id.id or False,
                    'alt_uom_qty': move.alt_uom_qty_actual,
                    'sequence': move.sequence
                    })
                invoice_vals['invoice_line_ids'].append((0, 0, line_vals))


            move = self.env['account.move'].sudo().with_context(default_move_type='in_invoice').create(invoice_vals)
            picking.billed = True
            picking.purchase_bill_id = move.id
        return self.action_view_bill()
    
    def action_view_bill(self):
        if not self.purchase_bill_id:
            self.create_st_bill()
        if self.purchase_bill_id:
            action = self.env['ir.actions.actions']._for_xml_id('account.action_move_in_invoice_type')
            form_view = [(self.env.ref('account.view_move_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = self.purchase_bill_id.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action
    
    def button_setqtys_incoming(self):
        sml = self.env['stock.move.line']
        for picking in self:
            if picking.serial_line_ids:
                for serial in picking.serial_line_ids:
                    serial_qty = serial.quantity
                    move_lines = sml.search([
                        ('product_id', '=', serial.product_id.id),
                        ('lot_id', '=', serial.lot_id.id),
                        ('picking_id', '=', picking.id),
                        ])
                    if move_lines:
                        move = move_lines[0].move_id
                        move_lines[0].write({'qty_done': move_lines[0].qty_done+serial_qty})
                        move.write({
                            'quantity_done': sum([line.qty_done for line in move.move_line_ids]),
                            'alt_uom_qty_actual': move.alt_uom_qty_actual+1
                            })
                    serial.scanned = True
        return True
    
    def action_check_availability_inbranch(self):
        for picking in self:
            flag = True
            if picking.serial_line_ids:
                picking.do_unreserve()
                self._cr.execute('delete from picking_serial_line where picking_id=%s'% (picking.id))
                self._cr.commit()
                # picking.serial_line_ids.unlink()
            if flag:
                picking.scanned_list = ''
                picking.serial_line_ids.unlink()
                psl = self.env['picking.serial.line']
                sml = self.env['stock.move.line']
                sales_orders = self.env['sale.order'].with_context(no_filter=True).search([
                    ('origin', '=', picking.origin),
                    ('state', 'in', ('sale', 'done')),
                    ])
                if not sales_orders:
                    raise UserError('No Sales Orders available against PO %s'%(picking.origin))
                if sales_orders and len(sales_orders.ids) > 1:
                    raise UserError('Multiple Sales Orders %s available against PO %s'%([sales_order.name for sales_order in sales_orders], picking.origin))
                product_ids = []
                
                pos = self.env['purchase.order'].search([('name', '=', picking.origin)])
                po = pos and pos[0] or False
                picking_in_ids = self.env['stock.picking'].with_context(no_filter=True).search([
                    ('origin', '=', picking.origin),
                    ('state', '=', 'done')
                    ]).ids
                if po:
                    for line in po.order_line:
                        if picking_in_ids:
                            prev_stock_moves = self.env['stock.move'].search([
                                ('product_id', '=', line.product_id.id),
                                ('alt_uom_id', '=', line.alt_uom_id.id),
                                ('picking_id', 'in', picking_in_ids)
                                ])
                            qty_received = sum([sm.alt_uom_qty_actual for sm in prev_stock_moves])
                        qty_received = 0.0
                        rem_qty = line.alt_uom_qty - qty_received
                        if rem_qty > 0:
                            if line.alt_uom_id.type == 'base':
                                rem_uom_qty = line.product_id.product_tmpl_id.weight_bag * rem_qty
                            elif line.alt_uom_id.type == 'smaller':
                                rem_uom_qty = line.product_id.product_tmpl_id.weight_belt * rem_qty
                            stock_moves = self.env['stock.move'].search([
                                ('product_id', '=', line.product_id.id),
                                ('alt_uom_id', '=', line.alt_uom_id.id),
                                ('picking_id', '=', picking.id)
                                ])
                            if stock_moves:
                                if stock_moves[0].alt_uom_qty != rem_qty:
                                    stock_moves[0].alt_uom_qty = rem_qty
                                    stock_moves[0].product_uom_qty = rem_uom_qty
                                    stock_moves[0].sl_no = line.sl_no
                                    stock_moves[0].sale_line_id = line.id
                                    stock_moves[0].sequence = line.sequence
                                    stock_moves[0].alt_uom_qty_reserved = 0
                            else:
                                stock_move = picking.move_ids_without_package[0].copy({
                                    'product_id': line.product_id.id,
                                    'alt_uom_id': line.alt_uom_id.id,
                                    'picking_id': picking.id,
                                    'alt_uom_qty': rem_qty,
                                    'product_uom_qty': rem_uom_qty,
                                    'picking_type_id': picking.picking_type_id.id,
                                    'location_id': picking.location_id.id,
                                    'location_dest_id': picking.location_dest_id.id,
                                    'product_uom': line.product_uom.id,
                                    'sl_no': line.sl_no,
                                    'purchase_line_id': line.id,
                                    'origin': po.name,
                                    'name': line.product_id.name_get()[0][1],
                                    'branch_id': po.branch_id.id,
                                    'state': 'confirmed',
                                    'sequence': line.sequence,
                                    'alt_uom_qty_reserved': 0
                                    })
                                    
                for move in picking.move_ids_without_package:
                    if move.alt_uom_id:
                        product_ids.append(move.product_id.id)
                    else:
                        psls = psl.search([
                            ('picking_id', '=', picking.id),
                            ('product_id', '=', move.product_id.id),
                            ])
                        psls.unlink()
                if sales_orders:
                    dns = self.with_context(no_branch_filter=True).search([
                        ('origin', '=', sales_orders[0].name),
                        ('picking_type_id.code', '=', 'outgoing'),
                        ('state', '=', 'done'),
                        ('branch_received', '!=', True)
                        ], order='date_done', limit=1)
                    if not dns:
                        raise UserError('No Delivery Orders available against PO %s - SO %s'%(picking.origin, sales_orders[0].name))
                    dn = dns[0]
                    grns = self.with_context(no_branch_filter=True).search([
                        ('origin', '=', picking.origin),
                        ('picking_type_id.code', '=', 'incoming'),
                        ('state', '=', 'done'),
                        ('id', '!=', picking.id)
                        ])
                    grn_sns = []
                    for grn in grns:
                        for serial in grn.serial_line_ids:
                            grn_sns.append(serial.serial_id.id)
                    serials_fetched = []
                    for serial in dn.serial_line_ids:
                        if serial.serial_id.product_id.id in product_ids:
                            if serial.serial_id.id not in grn_sns:
                                psl.create({
                                    'serial_id': serial.serial_id.id,
                                    'alt_uom_id': serial.alt_uom_id.id,
                                    'quantity': serial.quantity,
                                    'picking_id': picking.id
                                    })
                                serial.serial_id.write({'name': serial.serial_id.name.replace('\n', '').replace(' ', '')})
                                serials_fetched.append(serial.serial_id.id)
                    for move in picking.move_ids_without_package:
                        if not move.alt_uom_id:
                            psls = psl.search([
                                ('picking_id', '=', picking.id),
                                ('product_id', '=', move.product_id.id),
                                ])
                            psls.unlink()
                        mls = sml.search([('move_id', '=', move.id)])
                        mls.unlink()
                        psls = psl.search([
                            ('picking_id', '=', picking.id),
                            ('product_id', '=', move.product_id.id),
                            ])
                        if not psls:
                            continue
                        demand_qty = move.alt_uom_qty
                        bag_qty = len(psls.ids)
                        if bag_qty < demand_qty:
                            demand_qty = bag_qty
                        for i in range(demand_qty):
                            serial = psls[i]
                            lot_id = serial.lot_id.id
                            mls = sml.search([
                                ('move_id', '=', move.id),
                                ('product_id', '=', move.product_id.id),
                                ('lot_id', '=', lot_id)
                                ])
                            if mls:
                                pass
                            else:
                                sml.create({
                                    'move_id': move.id,
                                    'product_id': move.product_id.id,
                                    'lot_id': lot_id,
                                    'location_id': move.location_id.id, 
                                    'location_dest_id': move.location_dest_id.id,
                                    'picking_id': picking.id,
                                    'branch_id': picking.branch_id.id
                                    })
                    if serials_fetched:
                        dn.branch_received = True
                        picking.write({
                            'state': 'assigned',
                            'dn_ref': dn.name
                            })
        return True
    
    def do_unreserve(self):
        res = super(Picking, self).do_unreserve()
        for picking in self:
            for move in picking.move_ids_without_package:
                move.alt_uom_qty_actual = 0
                move.alt_uom_qty_reserved = 0
                for line in move.move_line_ids:
                    line.qty_done = 0
            if not 'rereserve' in picking._context:
                for serial in picking.serial_line_ids:
                    if serial.serial_line_out_id:
                        serial.serial_line_out_id.unlink()
                    serial.unlink()
            picking.scanned_list = ''
            if picking.dn_ref:
                dns = self.with_context(no_branch_filter=True).search([
                    ('name', '=', picking.dn_ref)])
                if dns:
                    dns[0].branch_received = False
        return res
    
    def action_clear_quantities_to_zero(self):
        res = super(Picking, self).action_clear_quantities_to_zero()
        for picking in self:
            picking.scanned_list = ''
            for move in self.move_ids_without_package:
                move.alt_uom_qty_actual = 0
            for serial in picking.serial_line_ids:
                serial.scanned = False
        return res
    
    def action_set_quantities_to_reservation(self):
        sml_obj = self.env['stock.move.line']
        for picking in self:
            for move in picking.move_ids_without_package:
                move.quantity_done = 0.0
                for move_line in move.move_line_ids:
                    move_line.qty_done = 0.0
            for serial in picking.serial_line_ids:
                serial.scanned = True
                moves = self.env['stock.move'].search([
                    ('product_id', '=', serial.product_id.id),
                    ('alt_uom_id', '=', serial.alt_uom_id.id),
                    ('picking_id', '=', picking.id)
                    ])
                if moves:
                    move = moves[0]
                    move_lines = sml_obj.search([
                        ('product_id', '=', serial.product_id.id),
                        ('lot_id', '=', serial.lot_id.id),
                        ('picking_id', '=', picking.id),
                        ('move_id', '=', move.id)
                        ])
                    if move_lines:
                        move_lines[0].write({'qty_done': move_lines[0].qty_done + serial.quantity})
                        move.write({
                            'quantity_done': sum([line.qty_done for line in move.move_line_ids]),
                            'alt_uom_qty_actual': move.alt_uom_qty_actual+1
                            })
                    else:
                        sml_obj.create({
                            'product_id': serial.product_id.id,
                            'lot_id': serial.lot_id.id,
                            'picking_id': picking.id,
                            'move_id': move.id,
                            'qty_done': serial.quantity
                            })
                        move.write({
                            'quantity_done': sum([line.qty_done for line in move.move_line_ids]),
                            'alt_uom_qty_actual': move.alt_uom_qty_actual+1
                            })
            if picking.picking_type_id.code == 'incoming' and picking.po_type == 'stock':
                dn = self.with_context(no_branch_filter=True).search([
                    ('name', '=', picking.dn_ref),
                    ('picking_type_id.code', '=', 'outgoing'),
                    ('state', '=', 'done')
                    ], order='date_done', limit=1)[0]
                for move in picking.move_ids_without_package:
                    dnsms = self.env['stock.move'].with_context(no_branch_filter=True).search([
                        ('product_id', '=', move.product_id.id),
                        ('alt_uom_id', '=', move.alt_uom_id.id),
                        ('picking_id', '=', dn.id)
                        ])
                    if dnsms:
                        move.price_unit = dnsms[0].price_unit
                        for move_line in move.move_line_ids:
                            dnsmls = self.env['stock.move.line'].with_context(no_branch_filter=True).search([
                                ('product_id', '=', move.product_id.id),
                                ('move_id', '=', dnsms[0].id),
                                ('lot_id', '=', move_line.lot_id.id)
                                ])
                            if dnsmls:
                                move_line.unit_cost = dnsmls[0].unit_cost
        return True
    
    def action_correction(self):
        for picking in self:
            for serial in picking.serial_line_ids:
                for sl in serial.serial_id:
                    for line in sl.line_ids:
                        if line.location_id.id in (4, 340):
                            line.unlink()
        return True
    
    def action_assign(self):
        for picking in self:
            if picking.picking_type_id.code == 'outgoing' and not 'normal_assign' in self._context:
                picking.action_assign_picking()
            else:
                return super(Picking, self).action_assign()
    
    def button_validate_reserve(self):
        psl_obj = self.env['picking.serial.line']
        sml_obj = self.env['stock.move.line']
        logger = logging.getLogger('button_validate_reserve:%s'%self.name)
        for picking in self:
            if picking.picking_type_id.code in ('outgoing', 'internal'):
                sequence = 1
                for move in picking.move_ids_without_package:
                    if picking.picking_type_id.code == 'internal':
                        move.sequence = sequence
                        sequence += 1
                    move.move_line_ids.unlink()
                    move.location_id = picking.location_id.id
                    psls = psl_obj.search([
                        ('picking_id', '=', picking.id),
                        ('product_id', '=', move.product_id.id),
                        ('alt_uom_id', '=', move.alt_uom_id.id)
                        ])
                    if not psls:
                        continue
                    qty_reserved = 0
                    if move.alt_uom_id.type == 'base':
                        qty_reserved = len(psls.ids)
                    lot_qty_dic = {}
                    for psl in psls:
                        if move.alt_uom_id.type != 'base':
                            qty_reserved += round(psl.quantity/move.product_id.weight_belt, 0)
                        lot_id = psl.lot_id.id
                        if lot_id in lot_qty_dic:
                            new_qty = lot_qty_dic[lot_id] + psl.quantity
                            lot_qty_dic.update({lot_id: new_qty})
                        else:
                            lot_qty_dic.update({lot_id: psl.quantity})
                    if move.alt_uom_id.type == 'base':
                        dem_qty = move.alt_uom_qty * move.product_id.weight_bag
                    else:
                        dem_qty = move.alt_uom_qty * move.product_id.weight_belt
                    reserved_uom_qty = 0
                    for lot_id in lot_qty_dic:
                        reserved_uom_qty += lot_qty_dic[lot_id]
                        sml_vals = {
                            'move_id': move.id,
                            'product_id': move.product_id.id,
                            'lot_id': lot_id,
                            'reserved_uom_qty': lot_qty_dic[lot_id],
                            'location_id': move.location_id.id, 
                            'location_dest_id': move.location_dest_id.id,
                            'picking_id': picking.id,
                            'branch_id': picking.branch_id.id
                            }
                        sml_obj.create(sml_vals)
                    if qty_reserved > 0:
                        move.state = 'assigned'
                        move.alt_uom_qty_reserved = qty_reserved
                        if dem_qty < reserved_uom_qty:
                            dem_qty = reserved_uom_qty
                        move.product_uom_qty = round(dem_qty, 3)
                
        return True
    
    def action_assign_picking_sfgrm(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                move.with_context(sfgrm_assign=True)._action_assign()
        return True
    
    def check_demand_qty(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                dem_qty = move.sale_line_id.alt_uom_qty - move.sale_line_id.alt_uom_qty_delivered
                if dem_qty > 0:
                    move.alt_uom_qty = dem_qty
                    move.product_uom_qty = move.sale_line_id.product_uom_qty - move.sale_line_id.qty_delivered
                else:
                    move.alt_uom_qty = 0
                    move.product_uom_qty = 0
                    move.state = 'draft'
                    move.unlink()
                    
        return True
    
    def action_assign_picking_fg(self):
        psl_obj = self.env['picking.serial.line']
        ss_obj = self.env['stock.serial']
        ssl_obj = self.env['stock.serial.location']
        for picking in self:
            if picking.picking_type_id.code in ('outgoing', 'internal'):
                if picking.picking_type_id.code == 'outgoing':
                    picking.check_demand_qty()
                fg = False
                sfg = False
                rm = False
                for move in picking.move_ids_without_package:
                    if move.product_id.categ_id.category_type == 'fg':
                        fg = True
                    elif move.product_id.categ_id.category_type == 'sfg':
                        sfg = True
                    elif move.product_id.categ_id.category_type == 'rm':
                        rm = True
                if not fg:
                    picking.with_context(normal_assign=True).action_assign()
                    return True
                if fg and (sfg or rm):
                    return True
                
                if fg:
                    serial_ids = []
                    for move in picking.move_ids_without_package:
                        product = move.product_id
                        balance_qty = move.alt_uom_qty - move.alt_uom_qty_reserved
                        logger.info('*'*100)
                        logger.info('%s-%s--balance_qty::%s'%(move.product_id.default_code,move.product_id.name,balance_qty))
                        logger.info('#'*100)
                        if balance_qty > 0:
                            location_serials = ssl_obj.search([
                                ('product_id', '=', product.id),
                                ('location_id', '=', picking.location_id.id),
                                ('id', 'not in', serial_ids)
                                ], order='date,serial_id,id')
                            logger.info(move.alt_uom_id.type)
                            if move.alt_uom_id.type == 'base':
                                logger.info('location_serials:%s-%s'%(move.product_id.default_code,location_serials))
                                for location_serial in location_serials:
                                    logger.info('sl_lots:%s'%location_serial.serial_id.name)
                                for location_serial in location_serials:
                                    serial = location_serial.serial_id
                                    logger.info('serial:%s'%serial.name)
                                    if not serial.id in serial_ids:
                                        loc_qty = round(serial.get_location_qty(picking.location_id.id), 3)
                                        available_qty = round(loc_qty - round(serial.quantity_reserved, 3), 3)
                                        logger.info('available_qty:%s'%available_qty)
                                        if available_qty > 0 and available_qty == round(serial.initial_qty, 3):
                                            psl_obj.create({
                                                'serial_id': serial.id,
                                                'picking_id': picking.id,
                                                'lot_id': serial.lot_id.id,
                                                'quantity': available_qty,
                                                'alt_uom_id': move.alt_uom_id.id
                                                })
                                            serial_ids.append(serial.id)
                                            balance_qty -= 1
                                        if balance_qty == 0:
                                            break
                            else:
                                logger.info('location_serials:%s-%s'%(move.product_id.default_code,location_serials))
                                belt_std_wt = round(product.weight_belt, 3)
                                for location_serial in location_serials:
                                    serial = location_serial.serial_id
                                    logger.info('serial:%s'%serial.name)
                                    if not serial.id in serial_ids:
                                        loc_qty = round(serial.get_location_qty(picking.location_id.id), 3)
                                        available_qty = round(loc_qty - round(serial.quantity_reserved, 3), 3)
                                        logger.info('available_qty:%s'%available_qty)
                                        if available_qty > 0:
                                            if available_qty != round(serial.initial_qty, 3):
                                                belt_qty = round(available_qty / belt_std_wt, 0)
                                                if belt_qty > 0:
                                                    belt_wt = round(available_qty / belt_qty, 3)
                                                    if balance_qty >= belt_qty:
                                                        psl_obj.create({
                                                            'serial_id': serial.id,
                                                            'picking_id': picking.id,
                                                            'lot_id': serial.lot_id.id,
                                                            'quantity': available_qty,
                                                            'alt_uom_id': move.alt_uom_id.id
                                                            })
                                                        serial_ids.append(serial.id)
                                                        balance_qty -= belt_qty
                                                    elif balance_qty < belt_qty:
                                                        psl_obj.create({
                                                            'serial_id': serial.id,
                                                            'picking_id': picking.id,
                                                            'lot_id': serial.lot_id.id,
                                                            'quantity': round(balance_qty*belt_wt, 3),
                                                            'alt_uom_id': move.alt_uom_id.id
                                                            })
                                                        serial_ids.append(serial.id)
                                                        balance_qty = 0
                                    if balance_qty == 0:
                                        break
                                logger.info('balance_qty_last:%s'%balance_qty)
                                logger.info('location_serials:%s'%location_serials)
                                if balance_qty > 0:
                                    for serial in location_serials:
                                        serial = location_serial.serial_id
                                        logger.info('location_serial:%s,serial:%s'%(location_serial.id,serial.name))
                                        if not serial.id in serial_ids:
                                            loc_qty = round(serial.get_location_qty(picking.location_id.id), 3)
                                            available_qty = round(loc_qty - round(serial.quantity_reserved, 3), 3)
                                            logger.info('available_qty:%s'%available_qty)
                                            if available_qty > 0 :
                                                if available_qty == round(serial.initial_qty, 3):
                                                    belt_qty = round(available_qty / belt_std_wt, 0)
                                                    belt_wt = round(available_qty / belt_qty, 3)
                                                    if balance_qty >= belt_qty:
                                                        psl_obj.create({
                                                            'serial_id': serial.id,
                                                            'picking_id': picking.id,
                                                            'lot_id': serial.lot_id.id,
                                                            'quantity': available_qty,
                                                            'alt_uom_id': move.alt_uom_id.id
                                                            })
                                                        serial_ids.append(serial.id)
                                                        balance_qty -= belt_qty
                                                    elif balance_qty < belt_qty:
                                                        psl_obj.create({
                                                            'serial_id': serial.id,
                                                            'picking_id': picking.id,
                                                            'lot_id': serial.lot_id.id,
                                                            'quantity': round(balance_qty*belt_wt, 3),
                                                            'alt_uom_id': move.alt_uom_id.id
                                                            })
                                                        serial_ids.append(serial.id)
                                                        balance_qty = 0
                                        if balance_qty == 0:
                                            break
                    picking.button_validate_reserve()
        return True
    
    def action_assign_picking(self):
        for picking in self:
            if picking.picking_type_id.code in ('outgoing', 'internal'):
                fg, sfg, rm = False, False, False
                if picking.picking_type_id.code == 'outgoing':
                    orders = self.env['sale.order'].search([('name', '=', picking.origin)])
                    order = orders and orders[0] or False
                    if order:
                        for line in order.order_line:
                            rem_qty = line.alt_uom_qty - line.alt_uom_qty_delivered
                            if rem_qty > 0:
                                if line.alt_uom_id.type == 'base':
                                    rem_uom_qty = line.product_id.product_tmpl_id.weight_bag * rem_qty
                                elif line.alt_uom_id.type == 'smaller':
                                    rem_uom_qty = line.product_id.product_tmpl_id.weight_belt * rem_qty
                                stock_moves = self.env['stock.move'].search([
                                    ('product_id', '=', line.product_id.id),
                                    ('alt_uom_id', '=', line.alt_uom_id.id),
                                    ('picking_id', '=', picking.id)
                                    ])
                                if stock_moves:
                                    if stock_moves[0].alt_uom_qty != rem_qty:
                                        stock_moves[0].alt_uom_qty = rem_qty
                                        stock_moves[0].product_uom_qty = rem_uom_qty
                                        stock_moves[0].sl_no = line.sl_no
                                        stock_moves[0].sale_line_id = line.id
                                        stock_moves[0].sequence = line.sequence
                                        stock_moves[0].alt_uom_qty_reserved = 0
                                else:
                                    stock_move = picking.move_ids_without_package[0].copy({
                                        'product_id': line.product_id.id,
                                        'alt_uom_id': line.alt_uom_id.id,
                                        'picking_id': picking.id,
                                        'alt_uom_qty': rem_qty,
                                        'product_uom_qty': rem_uom_qty,
                                        'picking_type_id': picking.picking_type_id.id,
                                        'location_id': picking.location_id.id,
                                        'location_dest_id': picking.location_dest_id.id,
                                        'product_uom': line.product_uom.id,
                                        'sl_no': line.sl_no,
                                        'sale_line_id': line.id,
                                        'origin': order.name,
                                        'name': line.product_id.name_get()[0][1],
                                        'branch_id': order.branch_id.id,
                                        'state': 'confirmed',
                                        'sequence': line.sequence,
                                        'alt_uom_qty_reserved': 0
                                        })
                                    
                for move in picking.move_ids_without_package:
                    if move.product_id.categ_id.category_type == 'fg':
                        fg = True
                    elif move.product_id.categ_id.category_type == 'sfg':
                        sfg = True
                    elif move.product_id.categ_id.category_type == 'rm':
                        rm = True
                if not fg:
                    picking.action_assign_picking_sfgrm()
                    return True
                if fg and not sfg and not rm:
                    picking.action_assign_picking_fg()
        return True
    
    def update_move_locations(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                move.location_id = picking.location_id.id
                move.location_dest_id = picking.location_dest_id.id
                for move_line in move.move_line_ids:
                    move_line.location_id = picking.location_id.id
                    move_line.location_dest_id = picking.location_dest_id.id
        return True
    
    @api.onchange('serial_number')
    def onchange_serial_number(self):
        sml = self.env['stock.move.line']
        psl = self.env['picking.serial.line']
        if self.serial_number:
            if self.picking_type_id.code == 'incoming':
                scanned_list = self.scanned_list.split(',')
                sn_list = [sl.serial_id.name.replace('\n', '').replace(' ', '') for sl in self.serial_line_ids]
                serial_number = self.serial_number.replace('\n', '').replace(' ', '')
                if serial_number not in sn_list:
                    raise UserError('Serial Number %s is not in the list.'%(self.serial_number))
                if serial_number in scanned_list:
                    raise UserError('Serial Number %s is already scanned.'%(self.serial_number))
                picking_id = int(str(self.id).split('NewId_')[1])
                serials = psl.with_context(no_filter=True).search([
                    ('serial_id.name', '=', serial_number),
                    ('picking_id', '=', picking_id)
                    ])
                if not serials:
                    raise UserError('Serial Number %s is not available.'%(self.serial_number))
                if serials:
                    serial_qty = serials[0].quantity
                    move_lines = sml.search([
                        ('product_id', '=', serials[0].product_id.id),
                        ('lot_id', '=', serials[0].lot_id.id),
                        ('picking_id', '=', picking_id),
                        ])
                    if move_lines:
                        move_line = move_lines[0]
                        qty_done = move_line.qty_done + serial_qty
                        move_line.write({'qty_done': qty_done})
                        move = move_line.move_id
                        move.write({
                            'quantity_done': sum([line.qty_done for line in move.move_line_ids]),
                            'alt_uom_qty_actual': move.alt_uom_qty_actual + 1
                            })
                        serials[0].scanned = True
                        self._cr.commit()
                self.serial_number = ''

            if self.picking_type_id.code in ('outgoing', 'internal'):
                scanned_list = self.scanned_list.split(',')
                sn_list = [sl.serial_id.name.replace('\n', '').replace(' ', '') for sl in self.serial_line_ids]
                serial_number = self.serial_number.replace('\n', '').replace(' ', '')
                if serial_number not in sn_list:
                    raise UserError('Serial Number %s is not in the list.'%(self.serial_number))
                if serial_number in scanned_list:
                    raise UserError('Serial Number %s is already scanned.'%(self.serial_number))
                picking_id = int(str(self.id).split('NewId_')[1])
                serials = psl.with_context(no_filter=True).search([
                    ('name', '=', serial_number),
                    ('picking_id', '=', picking_id)
                    ])
                if serials:
                    serial = serials[0]
                    serial_qty = serial.quantity
                    if serial.alt_uom_id.type == 'base':
                        qty_actual = 1
                    else:
                        belt_wt = serial.product_id.weight_belt
                        qty_actual = round(serial_qty / belt_wt, 0)
                    move_lines = sml.search([
                        ('product_id', '=', serial.product_id.id),
                        ('lot_id', '=', serial.lot_id.id),
                        ('picking_id', '=', picking_id),
                        ('move_id.alt_uom_id', '=', serial.alt_uom_id.id),
                        ])
                    if move_lines:
                        move_line = move_lines[0]
                        qty_done = move_line.qty_done + serial_qty
                        move_line.write({'qty_done': qty_done})
                        move = move_line.move_id
                        move.write({
                            'quantity_done': sum([line.qty_done for line in move.move_line_ids]),
                            'alt_uom_qty_actual': move.alt_uom_qty_actual + qty_actual
                            })
                        serial.scanned = True
                self.serial_number = ''
                self._cr.commit()

    def button_validate(self):
        psl = self.env['picking.serial.line']
        ssl = self.env['stock.serial.line']
        for picking in self:
            company = self.env.user.company_id
            if picking.picking_type_id.code in ('outgoing', 'internal'):
                product_wt_dic = {}
                sl_wt_dic = {}
                scanned_sls = []
                for sl in picking.serial_line_ids:
                    if sl.scanned:
                        if sl.serial_id.id in scanned_sls:
                            raise UserError('Serial Number %s is repeated'%(sl.serial_id.name))
                        scanned_sls.append(sl.serial_id.id)
                    if not sl.scanned:
                        sl.unlink()
                if picking.location_id.usage != 'internal':
                    continue
                for move in picking.move_ids_without_package:
                    done_qty = 0.0
                    for line in move.move_line_ids:
                        done_qty += line.qty_done
                        if not 'no_qty_check' in self._context:
                            if line.qty_done > 0:
                                if line.lot_id:
                                    domain = [
                                        ('branch_id', '=', picking.branch_id.id),
                                        ('location_id', '=', move.location_id.id),
                                        ('product_id', '=', move.product_id.id),
                                        ('lot_id', '=', line.lot_id.id)
                                        ]
                                    quants = self.env['stock.quant'].search(domain)
                                    if quants:
                                        if quants[0].quantity < line.qty_done:
                                            raise UserError('Only %s Available for %s in Location : %s in Lot : %s'%(round(quants[0].quantity, 3), move.product_id.name_get()[0][1], move.location_id.name, line.lot_id.name))
                                    else:
                                        quant = self.env['stock.quant'].create({
                                            'branch_id': picking.branch_id.id,
                                            'location_id': move.location_id.id,
                                            'product_id': move.product_id.id
                                            })
                                        if quant.quantity < line.qty_done:
                                            raise UserError('Only %s Available for %s in Location : %s in Lot : %s'%(round(quant.quantity, 3), move.product_id.name_get()[0][1], move.location_id.name, line.lot_id.name))
                                else:
                                    domain = [
                                        ('branch_id', '=', picking.branch_id.id),
                                        ('location_id', '=', move.location_id.id),
                                        ('product_id', '=', move.product_id.id),
                                        ]
                                    quants = self.env['stock.quant'].search(domain)
                                    if quants:
                                        if quants[0].quantity < line.qty_done:
                                            raise UserError('Only %s Available for %s in Location : %s'%(round(quants[0].quantity, 3), move.product_id.name_get()[0][1], move.location_id.name))
                                    else:
                                        quant = self.env['stock.quant'].create({
                                            'branch_id': picking.branch_id.id,
                                            'location_id': move.location_id.id,
                                            'product_id': move.product_id.id
                                            })
                                        if quant.quantity < line.qty_done:
                                            raise UserError('Stock Not Available for %s in Location : %s'%(move.product_id.name_get()[0][1], move.location_id.name))
                    move.quantity_done = done_qty
                for move in picking.move_ids_without_package:
                    if move.product_id.categ_id.category_type == 'fg':
                        total_weight = 0
                        for move_line in move.move_line_ids:
                            if move_line.qty_done > 0:
                                total_weight += move_line.qty_done
                                sl_lots = psl.search([
                                    ('picking_id', '=', picking.id),
                                    ('lot_id', '=', move_line.lot_id.id),
                                    ('alt_uom_id', '=', move.alt_uom_id.id)
                                    ])
                                # logger = logging.getLogger('button_validate:')
                                # logger.info('sl_lots:%s'%sl_lots)
                                if sl_lots:
                                    sl_lots_total = 0
                                    for sl_lot in sl_lots:
                                        sl_lots_total += round(sl_lot.quantity, 3)
                                    # logger.info('sl_lots_total:%s'%sl_lots_total)
                                    # logger.info('round(move_line.qty_done, 3):%s'%round(move_line.qty_done, 3))
                                    if round(sl_lots_total, 3) != round(move_line.qty_done, 3):
                                        raise UserError('Lot Numbers not matching for product %s'%(move_line.product_id.name))
                                else:
                                    raise UserError('Lot Numbers not matching for product %s'%(move_line.product_id.name))
                            
                            # lot_dic.update({move_line.lot_id.id: move_line.qty_done})
                        if move.product_id.id in product_wt_dic:
                            product_wt_dic.update({move.product_id.id: product_wt_dic[move.product_id.id]+total_weight})
                        else:
                            product_wt_dic.update({move.product_id.id: total_weight})
                for sl in picking.serial_line_ids:
                    sl_lots = psl.search([
                        ('picking_id', '=', picking.id),
                        ('serial_id', '=', sl.id)
                        ])
                    if len(sl_lots.ids) > 1:
                        raise UserError('%s repeated for product %s'%(sl.name, sl.product_id.name))
                    if sl.quantity == 0:
                        raise UserError('Cannot process Zero weight for %s for product %s'%(sl.name, sl.product_id.name))
                    if sl.product_id.id in sl_wt_dic:
                        sl_wt_dic.update({sl.product_id.id: sl_wt_dic[sl.product_id.id]+sl.quantity})
                    else:
                        sl_wt_dic.update({sl.product_id.id: sl.quantity})
                for move in picking.move_ids_without_package:
                    if move.product_id.id in sl_wt_dic:
                        if round(product_wt_dic[move.product_id.id], 3) != round(sl_wt_dic[move.product_id.id], 3):
                            raise UserError('Serial No. Weight not matching with Done Qty for %s'%(move.product_id.name))
                    
                for move in picking.move_ids_without_package:
                    if move.alt_uom_qty == move.alt_uom_qty_actual:
                        move.product_uom_qty = move.quantity_done
            if picking.picking_type_id.code == 'incoming':
                if picking.partner_id.is_branch and picking.branch_return:
                    for move in picking.move_ids_without_package:
                        move.write({
                            'location_id': picking.location_id.id,
                            'location_dest_id': picking.location_dest_id.id,
                            }) 
                        for move_line in move.move_line_ids:
                            move_line.write({
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                })
                if not picking.partner_id.is_branch:
                    for move in picking.move_ids_without_package:
                        if move.quantity_done > move.product_uom_qty:
                            raise UserError('Done Qty cannot be greater than Demand.')
            if picking.partner_id and picking.partner_id.is_branch and picking.picking_type_id.code == 'outgoing':
                branches = self.env['res.branch'].with_context(no_filter=True).search([('partner_id', '=', picking.partner_id.id)])
                inter_branch = branches and branches[0] or False
                if not inter_branch:
                    raise UserError('Branch not linked with %s.'%(picking.partner_id.name))
                    
                transit_location_ids = self.env['branch.location'].search([
                    ('branch_id', '=', self.branch_id.id),
                    ('inter_branch_id', '=', inter_branch.id)
                    ])
                transit_location_id = transit_location_ids and transit_location_ids[0].location_id.id or False
                if not transit_location_id:
                    raise UserError('Transit Location not Configured for %s in %s Branch.'%(inter_branch.name, self.branch_id.name))
                picking.location_dest_id = transit_location_id
                for move in picking.move_ids_without_package:
                    move.write({
                        'recompute': not move.recompute,
                        'location_dest_id': transit_location_id
                        })
                    for move_line in move.move_line_ids:
                        move_line.location_dest_id = transit_location_id
        res = super(Picking, self).button_validate()
        for picking in self:
            if picking.picking_type_id.code == 'outgoing':
                if picking.partner_id.is_branch:
                    location_dest_id = transit_location_id
                else:
                    location_dest_id = picking.location_dest_id.id
                for serial in picking.serial_line_ids:
                    sl_vals = {
                        'location_id': picking.location_id.id,
                        'location_dest_id': location_dest_id,
                        'date': picking.date_done and picking.date_done or fields.Datetime.now(),
                        'quantity': serial.quantity,
                        'serial_id': serial.serial_id.id
                        }
                    if serial.serial_line_out_id:
                        serial.serial_line_out_id.write(sl_vals)
                    else:
                        serial.serial_line_out_id = ssl.create(sl_vals).id
                    serial.reserved = False
                for move in picking.move_ids_without_package:
                    move.alt_uom_qty_reserved = 0
            elif picking.picking_type_id.code == 'internal':
                for serial in picking.serial_line_ids:
                    sl_vals = {
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'date': picking.date_done and picking.date_done or fields.Datetime.now(),
                        'quantity': serial.quantity,
                        'serial_id': serial.serial_id.id
                        }
                    if serial.serial_line_out_id:
                        serial.serial_line_out_id.write(sl_vals)
                    else:
                        serial.serial_line_out_id = ssl.create(sl_vals).id
                    serial.reserved = False
            elif picking.picking_type_id.code == 'incoming':
                if picking.partner_id.is_branch:
                    if picking.branch_return:
                        for serial in picking.serial_line_ids:
                            sl_vals = {
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'quantity': serial.quantity,
                                'serial_id': serial.serial_id.id
                                }
                            if serial.serial_line_out_id:
                                serial.serial_line_out_id.write(sl_vals)
                            else:
                                serial.serial_line_out_id = ssl.create(sl_vals).id
                    else:
                        branches = self.env['res.branch'].with_context(no_filter=True).search([('partner_id', '=', picking.partner_id.id)])
                        vendor_branch_id = branches and branches[0].id or False
                        if not vendor_branch_id:
                            raise UserError('Branch not linked with this Partner.')
                        for move in picking.move_ids_without_package:
                            if move.alt_uom_qty == move.alt_uom_qty_actual:
                                move.product_uom_qty = move.quantity_done
                        
                        transit_location_ids = self.env['branch.location'].search([
                            ('branch_id', '=', vendor_branch_id),
                            ('inter_branch_id', '=', self.branch_id.id)
                            ])
                        transit_location_id = transit_location_ids and transit_location_ids[0].location_id.id or False
                        customer_location_id = self.env['stock.location'].search([('usage', '=', 'customer')])[0].id
                        picking.update_unit_cost_grn()
                        new_moves = []
                        for move in picking.move_ids_without_package:
                            total_cost, total_qty = 0.0, 0.0
                            if 'Return of' in picking.origin:
                                for move_line in move.move_line_ids:
                                    src_picking = picking.origin.split('Return of ')[1]
                                    src_move_lines = self.env['stock.move.line'].search([
                                        ('product_id', '=', move.product_id.id),
                                        ('lot_id', '=', move_line.lot_id.id),
                                        ('move_id.picking_id.name', '=', src_picking)
                                        ])
                                    if src_move_lines:
                                        move_line_unit_cost = src_move_lines[0].unit_cost
                                        total_cost += round(move_line_unit_cost * move_line.qty_done, 2)
                                        total_qty += move_line.qty_done
                                        move_line.unit_cost = move_line_unit_cost
                                move_unit_cost = round(total_cost / total_qty, 3)
                                move.price_unit = move_unit_cost
                            if not move.branch_transit_created:
                                new_move = move.create_branch_transit_move(transit_location_id, customer_location_id, vendor_branch_id, picking, move)
                                new_moves.append(new_move)
                                move.branch_transit_created = True
                        for new_move in new_moves:
                            new_move._action_done()
                            for ac_move in new_move.account_move_ids:
                                ac_move.branch_id = vendor_branch_id
                        for serial in picking.serial_line_ids:
                            if serial.scanned:
                                if not serial.branch_transit_created:
                                    sl_line_id = ssl.create({
                                        'location_id': transit_location_id,
                                        'location_dest_id': customer_location_id,
                                        'date': picking.date_done and picking.date_done or fields.Datetime.now(),
                                        'quantity': serial.quantity,
                                        'serial_id': serial.serial_id.id,
                                        }).id
                                    serial.branch_transit_created = True
                                sl_vals = {
                                    'location_id': picking.location_id.id,
                                    'location_dest_id': picking.location_dest_id.id,
                                    'date': picking.date_done and picking.date_done or fields.Datetime.now(),
                                    'quantity': serial.quantity,
                                    'serial_id': serial.serial_id.id
                                    }
                                if serial.serial_line_out_id:
                                    serial.serial_line_out_id.write(sl_vals)
                                else:
                                    sl_line_id = ssl.create(sl_vals).id
                                    serial.serial_line_out_id = sl_line_id
                            else:
                                serial.unlink()
                else:
                    for serial in picking.serial_line_ids:
                        sl_vals = {
                            'location_id': picking.location_id.id,
                            'location_dest_id': picking.location_dest_id.id,
                            'date': picking.date_done and picking.date_done or fields.Datetime.now(),
                            'quantity': serial.quantity,
                            'serial_id': serial.serial_id.id
                            }
                        if serial.serial_line_out_id:
                            serial.serial_line_out_id.write(sl_vals)
                        else:
                            sl_line_id = ssl.create(sl_vals).id
                            serial.serial_line_out_id = sl_line_id
        if picking.company_id.branch_soprice_ok:
            if picking.picking_type_id.code == 'outgoing' and picking.partner_id.is_branch:
                picking.update_sales_price()
            # elif picking.picking_type_id.code == 'incoming' and picking.partner_id.is_branch:
            #     picking.update_unit_cost_grn()
        return res
    
    def update_unit_cost_grn(self):
        for picking in self:
            if picking.picking_type_id.code == 'incoming' and picking.partner_id and picking.partner_id.is_branch:
                if picking.dn_ref:
                    dns = self.with_context(no_branch_filter=True).search([('name', '=', picking.dn_ref)])
                    dn = dns and dns[0] or False
                    prod_lot_dic = {}
                    if dn:
                        for dn_move in dn.move_ids_without_package:
                            for dn_move_line in dn_move.move_line_ids:
                                prod_lot = '%s_%s'%(str(dn_move_line.product_id.id), str(dn_move_line.lot_id.id))
                                prod_lot_dic.update({prod_lot: dn_move_line.unit_cost})
                        for move in picking.move_ids_without_package:
                            if move.quantity_done == 0:
                                self._cr.execute('delete from stock_move where id=%s'% (move.id))
                                continue
                            total_cost, total_qty = 0.0, 0.0
                            for move_line in move.move_line_ids:
                                prod_lot = '%s_%s'%(str(move_line.product_id.id), str(move_line.lot_id.id))
                                unit_cost = prod_lot_dic.get(prod_lot, 0.0)
                                total_cost += round(unit_cost * move_line.qty_done, 2)
                                total_qty += move_line.qty_done
                                move_line.unit_cost = unit_cost
                            if total_qty > 0:
                                move.price_unit = round(total_cost / total_qty, 3)
        return True
    
    def update_svl_grn(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                for svl in move.stock_valuation_layer_ids:
                    svl.unit_cost = move.price_unit
                    svl.correct_svl_jv()
        return True
    
    def update_sales_price(self):
        svl_obj = self.env['stock.valuation.layer']
        for picking in self:
            if picking.picking_type_id.code == 'outgoing' and picking.partner_id and picking.partner_id.is_branch:
                picking.sale_order_id.action_unlock()
                for move in picking.move_ids_without_package:
                    if move.quantity_done > 0:
                        total_cost = 0.0
                        for move_line in move.move_line_ids:
                            lot_unit_cost = 0.0
                            total_lot_cost, total_lot_qty = 0.0, 0.0
                            svls = svl_obj.search([
                                ('product_id', '=', move.product_id.id),
                                ('lot_id', '=', move_line.lot_id.id),
                                ('create_date', '<', move_line.date),
                                ('quantity', '>', 0)
                                ], order='create_date desc')
                            if svls:
                                if len(svls.ids) == 1:
                                    lot_unit_cost = svls[0].unit_cost
                                else:
                                    for svl in svls:
                                        if svl.unit_cost > 0:
                                            total_lot_cost += svl.value
                                            total_lot_qty += svl.quantity
                                    if total_lot_qty > 0:
                                        lot_unit_cost = round(total_lot_cost / total_lot_qty, 3)
                            move_line.write({'unit_cost': lot_unit_cost})
                            total_cost += move_line.qty_done * lot_unit_cost
                        unit_cost = round(total_cost / move.quantity_done, 3)
                        move.write({'price_unit': unit_cost})
                        cost_delivered, qty_delivered = 0.0, 0.0
                        for so_move in move.sale_line_id.move_ids:
                            if so_move.state == 'done':
                                cost_delivered += so_move.price_unit * so_move.quantity_done
                                qty_delivered += so_move.quantity_done
                        total_cost += cost_delivered
                        unit_cost_delivered = round(total_cost / (move.quantity_done + qty_delivered), 3)
                        move.sale_line_id.write({'price_unit': unit_cost_delivered})
                picking.sale_order_id.action_done()
        return True
    
    def create_branch_transit_move(self):
        for picking in self:
            branches = self.env['res.branch'].with_context(no_filter=True).search([('partner_id', '=', picking.partner_id.id)])
            vendor_branch_id = branches and branches[0].id or False
            if not vendor_branch_id:
                raise UserError('Branch not linked with this Partner.')
            transit_location_ids = self.env['branch.location'].with_context(no_filter=True).search([
                ('branch_id', '=', vendor_branch_id),
                ('inter_branch_id', '=', self.branch_id.id)
                ])
            transit_location_id = transit_location_ids and transit_location_ids[0].location_id.id or False
            customer_location_id = self.env['stock.location'].search([('usage', '=', 'customer')])[0].id
            new_moves = []
            for move in self.move_ids_without_package:
                if move.quantity_done > 0:
                    new_move = move.with_context(no_branch_filter=True, force_date=move.date).create_branch_transit_move(transit_location_id, customer_location_id, vendor_branch_id, picking, move)
                    new_moves.append(new_move)
            for new_move in new_moves:
                new_move.with_context(no_branch_filter=True, force_date=move.date)._action_done()
                for ac_move in new_move.account_move_ids:
                    ac_move.branch_id = vendor_branch_id
        return True
    