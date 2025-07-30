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

from collections import defaultdict
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from cgitb import reset
from odoo.tools import float_is_zero, float_compare, float_round
import logging
logger = logging.getLogger(__name__)

class SerialNumbers(models.Model):
    _name = 'stock.serial'
    _description = 'Serial Numbers'
    _order = 'date,name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    def action_create_slall(self):
        return True
        serials = self.with_context(no_filter=True).search([])
        lots = list(set(serial.lot_id for serial in serials))
        for lot in lots:
            for serial in lot.serial_ids:
                serial.action_create_sl()
        return True
    
    def action_slnqty_correction(self):
        ssl_obj = self.env['stock.serial.line']
        for serial in self:
            ssls = ssl_obj.search([
                ('serial_id', '=', serial.id),
                ('create_uid', '=', 54),
                ('location_id', '=', 53),
                ('location_dest_id', '=', 14)
                ])
            if ssls:
                ssls.unlink()
        return True

    def action_clear_location_date(self, source_location_id, dest_location_id, date):
        for serial in self:
            qty = serial.get_location_qtydate(source_location_id, date)
            if qty == 0:
                pass
            else:
                if qty > 0:
                    location_id = source_location_id
                    location_dest_id = dest_location_id
                elif qty < 0:
                    location_id = dest_location_id
                    location_dest_id = source_location_id
                ssl_vals = {
                    'serial_id': serial.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'quantity': abs(qty),
                    'date': date
                    }
                self.env['stock.serial.line'].create(ssl_vals)
        return True

    def action_zero(self):
        return True
    
    def action_zero_location_date(self, location_id, date):
        for serial in self:
            inv_location_id = self.env.user.company_id.inv_location_id.id
            qty = serial.get_location_qtydate(location_id, date)
            if qty == 0:
                pass
            else:
                if qty > 0:
                    location_dest_id = inv_location_id
                elif qty < 0:
                    location_id = inv_location_id
                    location_dest_id = inv_location_id
                ssl_vals = {
                    'serial_id': serial.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'quantity': abs(qty),
                    'date': date
                    }
                self.env['stock.serial.line'].create(ssl_vals)
        return True
    
    def action_create_sl(self):
        location_ids = []
        ssl_obj = self.env['stock.serial.location']
        for serial in self:
            logger = logging.getLogger('SSL..')
            logger.info('%s'%(serial.name))
            for line in serial.line_ids:
                if line.location_dest_id.usage == 'internal':
                    location_ids.append(line.location_dest_id.id)
                if line.location_id.usage == 'internal':
                    location_ids.append(line.location_id.id)
            location_ids = list(set(location_ids))
            non_ssls = ssl_obj.with_context(no_filter=True).search([
                ('location_id', 'not in', location_ids),
                ('serial_id', '=', serial.id),
                ])
            if non_ssls:
                non_ssls.sudo().unlink()
            for location_id in location_ids:
                location = self.env['stock.location'].browse(location_id)
                location_qty = round(serial.get_location_qty(location_id), 3)
                ssls = ssl_obj.with_context(no_filter=True).search([
                    ('location_id', '=', location_id),
                    ('serial_id', '=', serial.id),
                    ('branch_id', '=', location.branch_id.id)
                    ])
                if ssls:
                    if location_qty == 0:
                        ssls.with_context(no_filter=True).unlink()
                    if location_qty != 0:
                        if len(ssls.ids) == 1:
                            ssls[0].write({'quantity': location_qty})
                        elif len(ssls.ids) > 1:
                            count = 1
                            for ssl in ssls:
                                if count == 1:
                                    ssl.write({'quantity': location_qty})
                                else:
                                    ssl.unlink()
                                count += 1
                else:
                    if location_qty != 0:
                        ssl_obj.with_context(no_filter=True).create({
                            'serial_id': serial.id,
                            'location_id': location_id,
                            'quantity': location_qty
                            })
        return True
    
    def action_print_label(self):
        return self.env.ref('etl_stock.action_serial_number_label').report_action(self)
    
    @api.model
    def _search1(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if 'no_filter' in self._context:
            pass
        else:
            args = args or []
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = [self.env.user.branch_id.id]
            if 'location_ids' in self._context:
                location_ids = self._context['location_ids']
            else:
                location_ids = self.env['stock.location'].search([
                    ('branch_id', 'in', branch_ids),
                    ('usage', '=', 'internal')
                    ]).ids
            if location_ids:
                in_query = """
                    select serial_id, sum(quantity) as qty
                    from stock_serial_line 
                    where location_dest_id in %s
                    group by serial_id;
                    """
                self.env.cr.execute(in_query, (tuple(location_ids),))
                qtys_in = self.env.cr.dictfetchall()
                in_dic = {}
                serial_ids = []
                for qty_in in qtys_in:
                    in_dic.update({qty_in['serial_id']: round(qty_in['qty'], 3)})
                    serial_ids.append(qty_in['serial_id'])
                out_query = """
                    select serial_id, sum(quantity) as qty
                    from stock_serial_line 
                    where location_id in %s
                    group by serial_id;
                    """
                self.env.cr.execute(out_query, (tuple(location_ids),))
                qtys_out = self.env.cr.dictfetchall()
                out_dic = {}
                for qty_out in qtys_out:
                    out_dic.update({qty_out['serial_id']: round(qty_out['qty'], 3)})
                    serial_ids.append(qty_out['serial_id'])
                qty_serial_ids = []
                serial_ids = list(set(serial_ids))
                for serial_id in serial_ids:
                    qty = round(in_dic.get(serial_id, 0.0) - out_dic.get(serial_id, 0.0), 3)
                    if qty != 0:
                        qty_serial_ids.append(serial_id)
                serial_ids = list(set(qty_serial_ids))
                args += [('id', 'in', serial_ids)]
        return super(SerialNumbers, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if 'no_filter' in self._context:
            pass
        else:
            args = args or []
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = [self.env.user.branch_id.id]
            if 'location_ids' in self._context:
                location_ids = self._context['location_ids']
            else:
                location_ids = self.env['stock.location'].search([
                    ('branch_id', 'in', branch_ids),
                    ('usage', '=', 'internal')
                    ]).ids
            if location_ids:

                query = """
                    select serial_id
                    from stock_serial_line
                    where location_id in %s OR location_dest_id in %s;
                    """
                self.env.cr.execute(query, (tuple(location_ids), tuple(location_ids),))
                serial_ids = [res['serial_id'] for res in self.env.cr.dictfetchall() if res['serial_id']]
                serial_ids = list(set(serial_ids))
                args += [('id', 'in', serial_ids)]
        return super(SerialNumbers, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)

    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if 'no_filter' in self._context:
            pass
        else:
            domain = domain or []
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = [self.env.user.branch_id.id]
            if 'location_ids' in self._context:
                location_ids = self._context['location_ids']
            else:
                location_ids = self.env['stock.location'].search([
                    ('branch_id', 'in', branch_ids),
                    ('usage', '=', 'internal')
                    ]).ids
            if location_ids:

                query = """
                    select serial_id
                    from stock_serial_line
                    where location_id in %s OR location_dest_id in %s;
                    """
                self.env.cr.execute(query, (tuple(location_ids), tuple(location_ids),))
                serial_ids = [res['serial_id'] for res in self.env.cr.dictfetchall() if res['serial_id']]
                serial_ids = list(set(serial_ids))
                domain += [('id', 'in', serial_ids)]
        return super(SerialNumbers, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

    @api.model
    def _read_group_raw1(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if 'no_filter' in self._context:
            pass
        else:
            domain = domain or []
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = [self.env.user.branch_id.id]
            if 'location_ids' in self._context:
                location_ids = self._context['location_ids']
            else:
                location_ids = self.env['stock.location'].search([
                    ('branch_id', 'in', branch_ids),
                    ('usage', '=', 'internal')
                    ]).ids
            if location_ids:
                in_query = """
                    select serial_id, sum(quantity) as qty
                    from stock_serial_line 
                    where location_dest_id in %s
                    group by serial_id;
                    """
                self.env.cr.execute(in_query, (tuple(location_ids),))
                qtys_in = self.env.cr.dictfetchall()
                in_dic = {}
                serial_ids = []
                for qty_in in qtys_in:
                    in_dic.update({qty_in['serial_id']: round(qty_in['qty'], 3)})
                    serial_ids.append(qty_in['serial_id'])
                out_query = """
                    select serial_id, sum(quantity) as qty
                    from stock_serial_line 
                    where location_id in %s
                    group by serial_id;
                    """
                self.env.cr.execute(out_query, (tuple(location_ids),))
                qtys_out = self.env.cr.dictfetchall()
                out_dic = {}
                for qty_out in qtys_out:
                    out_dic.update({qty_out['serial_id']: round(qty_out['qty'], 3)})
                    serial_ids.append(qty_out['serial_id'])
                serial_ids = list(set(serial_ids))
                qty_serial_ids = []
                for serial_id in serial_ids:
                    qty = round(in_dic.get(serial_id, 0.0) - out_dic.get(serial_id, 0.0), 3)
                    if qty != 0:
                        qty_serial_ids.append(serial_id)
                serial_ids = list(set(qty_serial_ids))
                domain += [('id', 'in', serial_ids)]
        return super(SerialNumbers, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    def print_labels(self):
        return self.env.ref('etl_stock.action_product_serial_print').report_action(self.id)
    
    def get_location_qtydate(self, location_id, date):
        line_obj = self.env['stock.serial.line']
        quantity_out, quantity_in = 0, 0
        in_lines = line_obj.search([
            ('location_dest_id', '=', location_id),
            ('serial_id', '=', self.id),
            ('date', '<=', date)
            ])
        for line in in_lines:
            quantity_in += line.quantity
        out_lines = line_obj.search([
            ('location_id', '=', location_id),
            ('serial_id', '=', self.id),
            ('date', '<=', date)
            ])
        for line in out_lines:
            quantity_out += line.quantity
        return round(quantity_in-quantity_out, 3)
    
    def get_location_qtys(self, product_id, location_id):
        location_ids = [location_id]
        product_ids = [product_id]
        if location_ids and product_ids:
            in_query = """
                select s.id as serial_id, sum(l.quantity) as qty
                from stock_serial_line l
                left join stock_serial s on l.serial_id=s.id
                where l.location_dest_id in %s and s.product_id in %s
                group by s.id;
                """
            self.env.cr.execute(in_query, (tuple(location_ids),tuple(product_ids),))
            qtys_in = self.env.cr.dictfetchall()
            serial_ids = []
            in_dic = {}
            for qty_in in qtys_in:
                in_dic.update({qty_in['serial_id']: round(qty_in['qty'], 3)})
                serial_ids.append(qty_in['serial_id'])
            out_query = """
                select s.id as serial_id, sum(l.quantity) as qty
                from stock_serial_line l
                left join stock_serial s on l.serial_id=s.id
                where l.location_id in %s and s.product_id in %s
                group by s.id;
                """
            self.env.cr.execute(out_query, (tuple(location_ids),tuple(product_ids),))
            qtys_out = self.env.cr.dictfetchall()
            out_dic = {}
            for qty_out in qtys_out:
                out_dic.update({qty_out['serial_id']: round(qty_out['qty'], 3)})
                serial_ids.append(qty_out['serial_id'])
            qty_list = []
            serial_ids = list(set(serial_ids))
            for serial_id in serial_ids:
                qty = round(in_dic.get(serial_id, 0.0) - out_dic.get(serial_id, 0.0), 3)
                if qty > 0:
                    qty_list.append(serial_id)
        return sorted(qty_list)
    
    def get_location_qty(self, location_id):
        line_obj = self.env['stock.serial.line']
        quantity_out, quantity_in = 0, 0
        in_lines = line_obj.search([
            ('location_dest_id', '=', location_id),
            ('serial_id', '=', self.id)
            ])
        for line in in_lines:
            quantity_in += line.quantity
        out_lines = line_obj.search([
            ('location_id', '=', location_id),
            ('serial_id', '=', self.id)
            ])
        for line in out_lines:
            quantity_out += line.quantity
        return round(quantity_in-quantity_out, 3)
    
    def _compute_quantity(self):
        for serial in self:
            line_obj = self.env['stock.serial.line']
            quantity_out, quantity_in = 0, 0
            in_lines = line_obj.search([
                ('serial_id', '=', serial.id),
                ('location_dest_id.usage', '=', 'internal')
                ])
            for line in in_lines:
                quantity_in += line.quantity
            out_lines = line_obj.search([
                ('serial_id', '=', serial.id),
                ('location_id.usage', '=', 'internal')
                ])
            for line in out_lines:
                quantity_out += line.quantity
            
            quantity_reserved = 0.0
            reserved_picking = ''
            reserved_lines = self.env['picking.serial.line'].search([
                ('serial_id', '=', serial.id),
                ('picking_id.state', 'not in', ('cancel', 'done')),
                ('picking_id.picking_type_id.code', '!=', 'incoming')
                ])
            for line in reserved_lines:
                quantity_reserved += round(line.quantity, 3)
                if reserved_picking:
                    reserved_picking += ', '+ line.picking_id.name
                else:
                    reserved_picking = line.picking_id.name
            serial.quantity_reserved = quantity_reserved
            serial.reserved_picking = reserved_picking
            
            serial.quantity_in = round(quantity_in, 3)
            serial.quantity_out = round(quantity_out, 3)
            quantity = round(quantity_in - quantity_out, 3)
            serial.quantity = quantity
            serial.quantity_available = round(quantity - quantity_reserved, 3)

    @api.depends('lot_id', 'lot_id.product_id', 'lot_id.product_id.default_code')
    def _compute_product(self):
        for serial in self:
            serial.product_id = serial.lot_id and serial.lot_id.product_id and serial.lot_id.product_id.id or False
            serial.product_reference = serial.lot_id and serial.lot_id.product_id and serial.lot_id.product_id.default_code or ''
            serial.categ_id = serial.lot_id and serial.lot_id.product_id and serial.lot_id.product_id.categ_id.id or False

    def _compute_reserved_quantity(self):
        for serial in self:
            quantity_reserved = 0.0
            reserved_picking = ''
            reserved_lines = self.env['picking.serial.line'].search([
                ('serial_id', '=', serial.id),
                ('picking_id.state', 'not in', ('cancel', 'done'))
                ])
            for line in reserved_lines:
                quantity_reserved += round(line.quantity, 3)
                if reserved_picking:
                    reserved_picking += ', '+ line.picking_id.name
                else:
                    reserved_picking = line.picking_id.name
            serial.quantity_reserved = quantity_reserved
            serial.reserved_picking = reserved_picking

    def _compute_initial_qty(self):
        for serial in self:
            initial_qty = 0
            if serial.initial_qty_manual > 0:
                initial_qty = serial.initial_qty_manual
            else:
                line_obj = self.env['stock.serial.line']
                in_lines = line_obj.search([('serial_id', '=', serial.id)], order='id')
                if in_lines:
                    initial_qty = in_lines[0].quantity
            serial.initial_qty = initial_qty

    @api.depends('recompute', 'line_ids', 'line_ids.location_id', 'line_ids.location_dest_id', 'line_ids.date')
    def _get_location(self):
        for serial in self:
            if serial.line_ids:
                location_id = False
                if round(serial.quantity, 3) == 0: 
                    location_id = serial.line_ids[0].location_dest_id.id
                elif round(serial.quantity, 3) == round(serial.initial_qty, 3):
                    location_id = serial.line_ids[0].location_dest_id.id
                else:
                    if round(serial.quantity, 3) > 0:
                        loc_dic = {}
                        for line in serial.line_ids:
                            if line.location_dest_id.usage == 'internal':
                                if line.location_dest_id.id in loc_dic:
                                    loc_dic.update({line.location_dest_id.id: loc_dic[line.location_dest_id.id]+round(line.quantity, 2)})
                                else:
                                    loc_dic.update({line.location_dest_id.id: round(line.quantity, 2)})
                            if line.location_id.usage == 'internal':
                                if line.location_id.id in loc_dic:
                                    loc_dic.update({line.location_id.id: loc_dic[line.location_id.id]-round(line.quantity, 2)})
                                else:
                                    loc_dic.update({line.location_id.id: -1*round(line.quantity, 2)})
                        for loc in loc_dic:
                            if loc_dic[loc] > 0:
                                location_id = loc
                serial.location_id = location_id
            else:
                serial.location_id = False
    
    def _get_locations(self):
        for serial in self:
            locations = ''
            if serial.loc_line_ids:
                for loc in serial.loc_line_ids:
                    if round(loc.quantity, 3) > 0:
                        locations += loc.location_id.name + ', '
                    elif round(loc.quantity, 3) < 0:
                        a = """
                        <font style="color: rgb(255, 0, 0);">%s</font>
                        """%loc.location_id.name
                        locations += a + ', '
                if locations:
                    locations = locations[:-2]
            #if not locations:
            #    if serial.line_ids:
            #        locations += serial.line_ids[0].location_dest_id.name
            serial.location = locations
    
    def _login_user(self):
        for serial in self:
            serial.login_user_id = self.env.user.user_access and self.env.user.id or False
            
    lot_id = fields.Many2one('stock.lot', 'Lot Number')
    product_id = fields.Many2one('product.product', 'Product', compute='_compute_product', store=True)
    categ_id = fields.Many2one('product.category', 'Product Category', compute='_compute_product', store=True)
    product_reference = fields.Char('Internal Reference', compute='_compute_product', store=True)
    quantity = fields.Float('Quantity', compute='_compute_quantity', digits=(16,3))
    quantity_available = fields.Float('Available Quantity', compute='_compute_quantity', digits=(16,3))
    quantity_in = fields.Float('Quantity In', compute='_compute_quantity', digits=(16,3))
    quantity_out = fields.Float('Quantity Out', compute='_compute_quantity', digits=(16,3))
    quantity_reserved = fields.Float('Reserved Qty', compute='_compute_quantity', digits=(16,3))
    initial_qty = fields.Float('Initial Qty', compute='_compute_initial_qty', digits=(16,3))
    name = fields.Char('Serial No.', required=True, tracking=True)
    line_ids = fields.One2many('stock.serial.line', 'serial_id', 'Lines', tracking=True)
    loc_line_ids = fields.One2many('stock.serial.location', 'serial_id', 'Location wise Stocks')
    initial_qty_manual = fields.Float('Std Weight(For Loose Stock)', tracking=True)
    loose_stock = fields.Boolean('Loose Stock?', tracking=True)
    date = fields.Date('Manufacturing Date', required=True, tracking=True)
    location = fields.Html('Location', compute='_get_locations')
    recompute = fields.Boolean('Recompute')
    reserved_picking = fields.Char('Reservations', compute='_compute_quantity')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    allow_sl_editing = fields.Boolean('Allow SL Editing', compute='_check_sl_access')
    
    @api.onchange('loose_stock')
    def onchange_loose_stock(self):
        if self.loose_stock:
            self.initial_qty_manual = self.product_id.weight_bag
        else:
            self.initial_qty_manual = 0
            
    def _check_sl_access(self):
        for sl in self:
            if self.user_has_groups('etl_base.group_sl_editing'):
                sl.allow_sl_editing = True
            else:
                sl.allow_sl_editing = False
                
    def unbuild(self):
        sll = self.env['stock.serial.location'].search([
            ('serial_id', '=', self.id)
            ])
        if sll:
            self.env['stock.serial.line'].create({
                'location_id': sll[0].location_id.id,
                'location_dest_id': self.env.user.company_id.unbuild_location_id.id,
                'date': fields.Datetime.now(),
                'quantity': sll[0].quantity,
                'serial_id': self.id
                }).id
        return True
    
    def get_pound(self, quantity):
        pound_qty = '%s (%s KG)'%(str(round(quantity * 2.20462, 3)), str(quantity))
        return pound_qty

class SerialNumberLines(models.Model):
    _name = 'stock.serial.line'
    _description = 'Serial Number Lines'
    _order = 'id desc'
    _rec_name = 'sl_name'
    
    @api.model_create_multi
    def create(self, vals_list):
        res = super(SerialNumberLines, self).create(vals_list)
        res.serial_id.action_create_sl()
        return res
    
    def unlink(self):
        serials = []
        for line in self:
            serials.append(line.serial_id)
        res = super(SerialNumberLines, self).unlink()
        serials = list(set(serials))
        for serial in serials:
            serial.action_create_sl()
        return res
    
    def write(self, vals):
        res = super(SerialNumberLines, self).write(vals)
        for sl in self:
            sl.serial_id.action_create_sl()
        return res
    
    @api.depends('serial_id', 'serial_id.lot_id', 'serial_id.date', 'serial_id.lot_id.product_id', 'location_dest_id', 'location_id')
    def _compute_product(self):
        for line in self:
            line.product_id = line.serial_id and line.serial_id.lot_id and line.serial_id.lot_id.product_id and line.serial_id.lot_id.product_id.id or False
            sl_name = ''
            if line.serial_id:
                sl_name = line.serial_id.name
            if line.location_id:
                sl_name += ':%s'%(line.location_id.name)
            if line.location_dest_id:
                sl_name += '->%s'%(line.location_dest_id.name)
            line.sl_name = sl_name
            line.manufacturing_date = line.serial_id and line.serial_id.date or False 
    
    def _compute_ref(self):
        pick_serial_obj = self.env['picking.serial.line']
        company = self.env.user.company_id
        for line in self:
            reference = ''
            if line.location_dest_id.id == company.unbuild_location_id.id:
                mrp_serials = self.env['mrp.serial'].search([('serial_id', '=', line.serial_id.id)])
                if mrp_serials:
                    reference = mrp_serials[0].production_id.name
            elif line.location_id.usage == 'production':
                mrp_serials = self.env['mrp.serial'].search([('serial_id', '=', line.serial_id.id)])
                if mrp_serials:
                    reference = mrp_serials[0].production_id.name
            elif line.location_id.usage == 'inventory':
                sms = self.env['stock.move.line'].search([
                    ('lot_id', '=', line.serial_id.lot_id.id),
                    ('location_id.usage', '=', 'inventory'),
                    ])
                if sms:
                    reference = sms[0].reference
            elif line.location_dest_id.usage == 'inventory':
                sms = self.env['stock.move.line'].search([
                    ('lot_id', '=', line.serial_id.lot_id.id),
                    ('location_dest_id.usage', '=', 'inventory'),
                    ])
                if sms:
                    reference = sms[0].reference
            elif line.location_id.usage == 'internal':
                pick_serials = pick_serial_obj.search([('serial_line_out_id', '=', line.id)])
                if pick_serials:
                    reference = pick_serials[0].picking_id.name
            elif line.location_id.usage == 'supplier':
                pick_serials = pick_serial_obj.search([('serial_line_out_id', '=', line.id)])
                if pick_serials:
                    reference = pick_serials[0].picking_id.name
            line.name = reference
            
    serial_id = fields.Many2one('stock.serial', 'Serial No.', ondelete='cascade')
    location_id = fields.Many2one('stock.location', 'Source')
    name = fields.Char('Reference', compute='_compute_ref')
    location_dest_id = fields.Many2one('stock.location', 'Destination')
    quantity = fields.Float('Quantity', digits=(16,3))
    product_id = fields.Many2one('product.product', 'Product', compute='_compute_product', store=True)
    sl_name = fields.Char('SL Name', compute='_compute_product', store=True)
    date = fields.Datetime('Date', default=fields.Datetime.now, required=False)
    manufacturing_date = fields.Date('Manufacturing Date', compute='_compute_product', store=True)
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'sll_menu' in self._context:
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = self.env.user.branch_ids.ids
            location_ids = self.env['stock.location'].search([
                ('branch_id', 'in', branch_ids),
                ('usage', '=', 'internal')
                ]).ids
            args += ['|', ('location_id', 'in', location_ids), ('location_dest_id', 'in', location_ids)]
        return super(SerialNumberLines, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'sll_menu' in self._context:
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = self.env.user.branch_ids.ids
            location_ids = self.env['stock.location'].search([
                ('branch_id', 'in', branch_ids),
                ('usage', '=', 'internal')
                ]).ids
            domain += ['|', ('location_id', 'in', location_ids), ('location_dest_id', 'in', location_ids)]
        return super(SerialNumberLines, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
class SerialLocations(models.Model):
    _name = 'stock.serial.location'
    _description = 'Location-wise Serial Numbers'
    _order = 'date,serial_id'
    
    
    def action_correct_outs3(self):
        for serial in self:
            psl_obj = self.env['picking.serial.line']
            ssl_obj = self.env['stock.serial.line']
            mrpsl_obj = self.env['mrp.serial']
            in_ssls = ssl_obj.search([
                ('location_id', '=', 15),
                ('location_dest_id', '=', serial.location_id.id),
                ('serial_id', '=', serial.serial_id.id),
                ])
            logger = logging.getLogger('SSL..')
            logger.info('%s'%(serial.serial_id.name))
            logger.info('in_ssls:%s'%(in_ssls))
            if in_ssls:
                mrp_sls = mrpsl_obj.search([
                    ('name', '=', serial.serial_id.name),
                    ('production_id.product_id', '=', serial.product_id.id)
                    ])
                if mrp_sls:
                    mrp = mrp_sls[0].production_id
                    date = mrp.move_finished_ids and mrp.move_finished_ids[0].date or fields.Date.today()
                    ssl_vals = {
                        'location_id': 14,
                        'location_dest_id': serial.location_id.id,
                        'date': date,
                        'quantity': mrp_sls[0].quantity,
                        'serial_id': serial.serial_id.id,
                        'name': mrp.name
                        }
                    ssl_obj.create(ssl_vals)
            if not in_ssls:
                mrp_sls = mrpsl_obj.search([
                    ('name', '=', serial.serial_id.name),
                    ('production_id.product_id', '=', serial.product_id.id)
                    ])
                logger.info('mrp_sls:%s'%(mrp_sls))
                if mrp_sls:
                    mrp = mrp_sls[0].production_id
                    date = mrp.move_finished_ids and mrp.move_finished_ids[0].date or fields.Date.today()
                    ssl_vals = {
                        'location_id': 15,
                        'location_dest_id': serial.location_id.id,
                        'date': date,
                        'quantity': mrp_sls[0].quantity,
                        'serial_id': serial.serial_id.id,
                        'name': mrp.name
                        }
                    ssl_obj.create(ssl_vals)
                    logger.info('ssl_vals:%s'%(ssl_vals))
                else:
                    smls = self.env['stock.move.line'].search([
                        ('product_id', '=', serial.product_id.id),
                        ('lot_id', '=', serial.lot_id.id),
                        ('state', '=', 'done'),
                        ('location_dest_id', '=', serial.location_id.id),
                        ('location_id', '=', 14),
                        ], order='date', limit=1)
                    logger.info('smls:%s'%(smls))
                    if smls:
                        date = smls[0].date
                        ssl_vals = {
                            'location_id': 14,
                            'location_dest_id': serial.location_id.id,
                            'date': date,
                            'quantity': abs(serial.quantity),
                            'serial_id': serial.serial_id.id,
                            'name': 'Opening Stock'
                            }
                        ssl_obj.create(ssl_vals)
                        logger.info('ssl_vals:%s'%(ssl_vals))
                        
            psls = psl_obj.search([
                ('serial_id', '=', serial.serial_id.id),
                ('picking_id.state', '=', 'done'),
                ])
            for psl in psls: 
                picking = psl.picking_id
                ssl_vals = {
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'date': picking.date_done,
                    'quantity': psl.quantity,
                    'serial_id': serial.serial_id.id
                    }
                serial_line_id = ssl_obj.create(ssl_vals).id
                psl.serial_line_out_id = serial_line_id
        return True

    def action_correct_slno_branch(self):
        for serial in self:
            psl_obj = self.env['picking.serial.line']
            ssl_obj = self.env['stock.serial.line']
            psls = psl_obj.with_context(no_filter=True).search([
                ('serial_id', '=', serial.serial_id.id),
                ('picking_id.state', '=', 'done'),
                ('picking_id.picking_type_id.code', '=', 'incoming')
                ])
            if psls:
                psl = psls[0]
                picking = psl.picking_id
                in_ssl_vals = {
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'date': picking.date_done,
                    'quantity': psl.quantity,
                    'serial_id': serial.serial_id.id
                    }
                in_ssls = ssl_obj.search([
                    ('location_id', '=', picking.location_id.id),
                    ('location_dest_id', '=', picking.location_dest_id.id),
                    ('serial_id', '=', serial.serial_id.id)
                    ])
                if in_ssls:
                    in_ssls[0].write(in_ssl_vals)
                    psl.serial_line_out_id = in_ssls[0].id
                else:
                    serial_line_id = ssl_obj.create(in_ssl_vals).id
                    psl.serial_line_out_id = serial_line_id
                
                out_ssl_vals = {
                    'location_id': serial.location_id.id,
                    'location_dest_id': 5,
                    'date': picking.date_done,
                    'quantity': psl.quantity,
                    'serial_id': serial.serial_id.id
                    }
                out_ssls = ssl_obj.search([
                    ('location_id', '=', serial.location_id.id),
                    ('location_dest_id', '=', 5),
                    ('serial_id', '=', serial.serial_id.id)
                    ])
                if out_ssls:
                    out_ssls[0].write(out_ssl_vals)
                else:
                    serial_line_id = ssl_obj.create(out_ssl_vals).id
        return True

    def action_correct_outs(self):
        for serial in self:
            psl_obj = self.env['picking.serial.line']
            ssl_obj = self.env['stock.serial.line']
            mrpsl_obj = self.env['mrp.serial']
            in_ssls = ssl_obj.search([
                ('location_id', '=', 15),
                ('location_dest_id', '=', serial.location_id.id),
                ('serial_id', '=', serial.serial_id.id),
                ])
            logger = logging.getLogger('SSL..')
            logger.info('%s'%(serial.serial_id.name))
            logger.info('in_ssls:%s'%(in_ssls))
            if in_ssls:
                mrp_sls = mrpsl_obj.search([
                    ('name', '=', serial.serial_id.name),
                    ('production_id.product_id', '=', serial.product_id.id)
                    ])
                if mrp_sls:
                    mrp = mrp_sls[0].production_id
                    date = mrp.move_finished_ids and mrp.move_finished_ids[0].date or fields.Date.today()
                    ssl_vals = {
                        'location_id': 14,
                        'location_dest_id': serial.location_id.id,
                        'date': date,
                        'quantity': mrp_sls[0].quantity,
                        'serial_id': serial.serial_id.id,
                        'name': mrp.name
                        }
                    ssl_obj.create(ssl_vals)
            if not in_ssls:
                mrp_sls = mrpsl_obj.search([
                    ('name', '=', serial.serial_id.name),
                    ('production_id.product_id', '=', serial.product_id.id)
                    ])
                logger.info('mrp_sls:%s'%(mrp_sls))
                if mrp_sls:
                    mrp = mrp_sls[0].production_id
                    date = mrp.move_finished_ids and mrp.move_finished_ids[0].date or fields.Date.today()
                    ssl_vals = {
                        'location_id': 15,
                        'location_dest_id': serial.location_id.id,
                        'date': date,
                        'quantity': mrp_sls[0].quantity,
                        'serial_id': serial.serial_id.id,
                        'name': mrp.name
                        }
                    ssl_obj.create(ssl_vals)
                    logger.info('ssl_vals:%s'%(ssl_vals))
                else:
                    smls = self.env['stock.move.line'].search([
                        ('product_id', '=', serial.product_id.id),
                        ('lot_id', '=', serial.lot_id.id),
                        ('state', '=', 'done'),
                        ('location_dest_id', '=', serial.location_id.id),
                        ('location_id', '=', 14),
                        ], order='date', limit=1)
                    logger.info('smls:%s'%(smls))
                    if smls:
                        date = smls[0].date
                        ssl_vals = {
                            'location_id': 14,
                            'location_dest_id': serial.location_id.id,
                            'date': date,
                            'quantity': abs(serial.quantity),
                            'serial_id': serial.serial_id.id,
                            'name': 'Opening Stock'
                            }
                        ssl_obj.create(ssl_vals)
                        logger.info('ssl_vals:%s'%(ssl_vals))

        return True

    def action_correct_outs2(self):
        for serial in self:
            psl_obj = self.env['picking.serial.line']
            ssl_obj = self.env['stock.serial.line']
            mrpsl_obj = self.env['mrp.serial']
            in_ssls = ssl_obj.search([
                ('location_id', '=', 15),
                ('location_dest_id', '=', serial.location_id.id),
                ('serial_id', '=', serial.serial_id.id),
                ])
            if not in_ssls:
                mrp_sls = mrpsl_obj.search([
                    ('name', '=', serial.serial_id.name),
                    ('production_id.product_id', '=', serial.product_id.id)
                    ])
                if mrp_sls:
                    mrp = mrp_sls[0].production_id
                    date = mrp.move_finished_ids and mrp.move_finished_ids[0].date or fields.Date.today()
                    ssl_vals = {
                        'location_id': 15,
                        'location_dest_id': serial.location_id.id,
                        'date': date,
                        'quantity': mrp_sls.quantity,
                        'serial_id': serial.serial_id.id,
                        'name': mrp.name
                        }
                else:
                    smls = self.env['stock.move.line'].search([
                        ('product_id', '=', serial.product_id.id),
                        ('lot_id', '=', serial.lot_id.id),
                        ('state', '=', 'done'),
                        ('location_dest_id', '=', serial.location_id.id),
                        ('location_id', '=', 14),
                        ], order='date', limit=1)
                    if smls:
                        date = smls[0].date
                        ssl_vals = {
                            'location_id': 14,
                            'location_dest_id': serial.location_id.id,
                            'date': date,
                            'quantity': abs(serial.quantity),
                            'serial_id': serial.serial_id.id,
                            'name': 'Opening Stock'
                            }
                        ssl_obj.create(ssl_vals)

        return True
    
    def action_correct_slno_transit(self):
        for serial in self:
            psl_obj = self.env['picking.serial.line']
            ssl_obj = self.env['stock.serial.line']

            ssloc_id = serial.id
            if serial.quantity < 0:
                psls = psl_obj.search([
                    ('serial_id', '=', serial.serial_id.id),
                    ('picking_id.state', '=', 'done'),
                    ('picking_id.picking_type_id.code', '=', 'outgoing')
                    ])
                if psls:
                    psl = psls[0]
                    picking = psl.picking_id
                    ssl_vals = {
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'date': picking.date_done,
                        'quantity': psl.quantity,
                        'serial_id': serial.serial_id.id,
                        'name': picking.name
                        }
                    ssls = ssl_obj.search([
                        ('location_id', '=', picking.location_id.id),
                        ('location_dest_id', '=', picking.location_dest_id.id),
                        ('serial_id', '=', serial.serial_id.id)
                        ])
                    if ssls:
                        ssls[0].write(ssl_vals)
                        psl.serial_line_out_id = ssls[0].id
                    else:
                        serial_line_id = ssl_obj.create(ssl_vals).id
                        psl.serial_line_out_id = serial_line_id
            ssloc_ids = self.search([('id', '=', ssloc_id)]).ids
            if not ssloc_ids:
                continue
            ssls1 = ssl_obj.search([
                ('location_id', '=', 14),
                ('location_dest_id', '=', 14),
                ('serial_id', '=', serial.serial_id.id)
                ])
            if ssls1:
                ssls1.unlink()
            ssls2 = ssl_obj.search([
                ('location_id', '=', 53),
                ('location_dest_id', '=', 14),
                ('serial_id', '=', serial.serial_id.id)
                ])
            if ssls2:
                ssls2.unlink()
            ssls3 = ssl_obj.search([
                ('location_id', '=', serial.location_id.id),
                ('location_dest_id', '=', 5),
                ('serial_id', '=', serial.serial_id.id)
                ])
            if ssls3:
                if len(ssls3.ids) > 1:
                    ssls3[0].unlink()
        return True

    def get_qty_date(self, product_ids, location_id, date):
        in_query = """
            select serial_id, sum(quantity) as qty
            from stock_serial_line 
            where location_dest_id=%s AND date<=%s AND product_id in %s
            group by serial_id;
            """
        self.env.cr.execute(in_query, (location_id, date, tuple(product_ids)))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        serial_ids = []
        for qty_in in qtys_in:
            serial_ids.append(qty_in['serial_id'])
            in_dic.update({qty_in['serial_id']: round(qty_in['qty'], 3)})
        out_query = """
            select serial_id, sum(quantity) as qty
            from stock_serial_line 
            where location_id=%s AND date<=%s AND product_id in %s
            group by serial_id;
            """
        self.env.cr.execute(out_query, (location_id, date, tuple(product_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            serial_ids.append(qty_out['serial_id'])
            out_dic.update({qty_out['serial_id']: round(qty_out['qty'], 3)})
        serial_ids = list(set(serial_ids))
        qty_dic = {}
        for serial_id in serial_ids:
            qty_dic.update({serial_id: in_dic.get(serial_id, 0.0) - out_dic.get(serial_id, 0.0)})
        return qty_dic 
    
    def get_ssl_qtys(self, product_ids, location_id):
        in_query = """
            select serial_id, sum(quantity) as qty
            from stock_serial_line 
            where location_dest_id=%s AND product_id in %s
            group by serial_id;
            """
        self.env.cr.execute(in_query, (location_id, tuple(product_ids)))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        serial_ids = []
        for qty_in in qtys_in:
            serial_ids.append(qty_in['serial_id'])
            in_dic.update({qty_in['serial_id']: round(qty_in['qty'], 3)})
        out_query = """
            select serial_id, sum(quantity) as qty
            from stock_serial_line 
            where location_id=%s AND product_id in %s
            group by serial_id;
            """
        self.env.cr.execute(out_query, (location_id, tuple(product_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            serial_ids.append(qty_out['serial_id'])
            out_dic.update({qty_out['serial_id']: round(qty_out['qty'], 3)})
        serial_ids = list(set(serial_ids))
        qty_dic = {}
        for serial_id in serial_ids:
            qty_dic.update({serial_id: in_dic.get(serial_id, 0.0) - out_dic.get(serial_id, 0.0)})
        return qty_dic 
    
    def action_correct_quants(self):
        serials = self.search([])
        location_ids = []
        lot_ids = []
        for serial in serials:
            location_ids.append(serial.location_id.id)
            lot_ids.append(serial.lot_id.id)
        location_ids = list(set(location_ids))
        lot_ids = list(set(lot_ids))
        for location_id in location_ids:
            for lot_id in lot_ids:
                serials = self.search([
                    ('lot_id', '=', lot_id),
                    ('location_id', '=', location_id)
                    ])
                qty = sum([round(serial.quantity, 3) for serial in serials])
                quants = self.env['stock.quant'].search([
                    ('lot_id', '=', lot_id),
                    ('location_id', '=', location_id)
                    ])
                if quants:
                    self._cr.execute("""update stock_quant set quantity='%s' where id=%s"""% (qty, quants[0].id))
        return True
    
    def action_correct_quants2(self):
        quants = self.env['stock.quant'].search([
            ('location_id.usage', '=', 'internal')
            ])
        for quant in quants:
            serials = self.search([
                ('lot_id', '=', quant.lot_id.id),
                ('location_id', '=', quant.location_id.id)
                ])
            if not serials:
                self._cr.execute("""update stock_quant set quantity=0 where id=%s"""%quant.id)
        return True
    
    def action_update_allbranch(self):
        branch_ids = self._context['allowed_branch_ids']
        location_ids = self.env['stock.location'].search([('branch_id', 'in', branch_ids), ('usage', '=', 'internal')]).ids
        location_ids = list(set(location_ids))
        logger = logging.getLogger('SSL Recalculation..')
        self._cr.execute("""select product_id from stock_quant where location_id in %s""",(tuple(location_ids),))
        product_ids = [res['product_id'] for res in self.env.cr.dictfetchall()]
        self._cr.execute("""select id from stock_serial where product_id in %s""",(tuple(product_ids),))
        serials = [res['id'] for res in self.env.cr.dictfetchall()]
        total_count = len(serials)
        count = 1
        for serial_id in serials:
            logger.info('%s/%s'%(count, total_count))
            serial = self.env['stock.serial'].browse(serial_id)
            serial.action_create_sl()
            count += 1
        return True
    
    def action_update_lot(self):
        logger = logging.getLogger('SSL Recalculation..')
        for serial in self.lot_id.serial_ids:
            serial.action_create_sl()
        return True
    
    def action_update_product(self):
        logger = logging.getLogger('SSL Recalculation..')
        sls = self.search([('product_id', '=', self.product_id.id)])
        lots = []
        for sl in sls:
            lots.append(sl.lot_id)
        for lot in list(set(lots)):
            for serial in lot.serial_ids:
                serial.action_create_sl()
        return True
    
    def action_update_branch(self):
        location_ids = self.env['stock.location'].search([
            ('branch_id', '=', self.branch_id.id), 
            ('usage', '=', 'internal')
            ]).ids
        location_ids = list(set(location_ids))
        logger = logging.getLogger('SSL Recalculation..')
        # self._cr.execute("""select product_id from stock_quant where location_id in %s""",(tuple(location_ids),))
        # product_ids = [res['product_id'] for res in self.env.cr.dictfetchall()]
        self._cr.execute("""select serial_id from stock_serial_location where location_id in %s""",(tuple(location_ids),))
        serials = [res['serial_id'] for res in self.env.cr.dictfetchall()]
        count = 1
        serials = list(set(serials))
        total_count = len(serials)
        for serial_id in serials:
            logger.info('%s/%s'%(count, total_count))
            serial = self.env['stock.serial'].browse(serial_id)
            serial.action_create_sl()
            count += 1
        return True
    
    def action_open_product(self):
        self.ensure_one()
        if self.serial_id:
            return {
                'res_model': 'product.product',
                'type': 'ir.actions.act_window',
                'views': [[False, "form"]],
                'res_id': self.product_id.id,
                }
            
    def action_open_lot(self):
        self.ensure_one()
        if self.serial_id:
            return {
                'res_model': 'stock.lot',
                'type': 'ir.actions.act_window',
                'views': [[False, "form"]],
                'res_id': self.lot_id.id,
                }
            
    def action_open_reference(self):
        self.ensure_one()
        if self.serial_id:
            return {
                'res_model': 'stock.serial',
                'type': 'ir.actions.act_window',
                'views': [[False, "form"]],
                'res_id': self.serial_id.id,
                }
        
    def _compute_qty(self):
        for loc in self:
            quantity = 0
            if loc.location_id.id and loc.serial_id.id:
                quantity = loc.serial_id.get_location_qty(loc.location_id.id)
            loc.quantity = round(quantity, 3)
    
    @api.depends('location_id', 'location_id.branch_id', 'serial_id', 'serial_id.date', 'serial_id.lot_id', 'serial_id.lot_id.product_id', 'serial_id.lot_id.product_id.default_code')
    def _compute_product(self):
        for loc in self:
            serial = loc.serial_id
            loc.date = serial.date
            loc.lot_id = serial.lot_id and serial.lot_id.id or False
            loc.product_id = serial.lot_id and serial.lot_id.product_id and serial.lot_id.product_id.id or False
            loc.product_reference = serial.lot_id and serial.lot_id.product_id and serial.lot_id.product_id.default_code or ''
            loc.categ_id = serial.lot_id and serial.lot_id.product_id and serial.lot_id.product_id.categ_id.id or False
            loc.branch_id = loc.location_id and loc.location_id.branch_id and loc.location_id.branch_id.id or False  
            
    def _login_user(self):
        for location in self:
            location.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    serial_id = fields.Many2one('stock.serial', 'Serial Number', ondelete='cascade')
    location_id = fields.Many2one('stock.location', 'Location', required=True)
    quantity = fields.Float('Quantity', digits=(16,3))
    lot_id = fields.Many2one('stock.lot', 'Lot Number', compute='_compute_product', store=True)
    product_id = fields.Many2one('product.product', 'Product', compute='_compute_product', store=True)
    categ_id = fields.Many2one('product.category', 'Product Category', compute='_compute_product', store=True)
    product_reference = fields.Char('Internal Reference', compute='_compute_product', store=True)
    branch_id = fields.Many2one('res.branch', 'Branch', compute='_compute_product', store=True)
    date = fields.Date('Manufacturing Date', compute='_compute_product', store=True)
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'no_filter' in self._context:
            branch_ids = self.env['res.branch'].search([]).ids
        else:
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = self.env.user.branch_ids.ids
        location_ids = self.env['stock.location'].search([
            ('branch_id', 'in', branch_ids),
            ('usage', '=', 'internal')
            ]).ids
        args += [('location_id', 'in', location_ids)]
        # self._cr.execute("""select id,serial_id,location_id from stock_serial_location where location_id in %s""",(tuple(location_ids),))
        # sl_list, dup_list = [], []
        # for sl in self.env.cr.dictfetchall():
        #     sl_loc = '%s_%s'%(str(sl['serial_id']), str(sl['location_id']))
        #     if sl_loc in sl_list:
        #         dup_list.append(sl['id'])
        #     else:
        #         if self.env['stock.serial'].browse(sl['serial_id']).get_location_qty(sl['location_id']) > 0:
        #             sl_list.append(sl_loc)
        #         else:
        #             dup_list.append(sl['id'])
        # lot_ids = []
        # for sl_id in dup_list:
        #     lot_id = self.env['stock.serial'].browse(sl_id).lot_id.id
        #     lot_ids.append(lot_id)
        # lot_ids = list(set(lot_ids))
        # for lot_id in lot_ids:
        #     self.env['stock.lot'].browse(lot_id).action_create_sl()
        # if dup_list:
        #     args += [('id', 'not in', dup_list)]
        res = super(SerialLocations, self)._search(args, offset=offset, limit=limit, order=order, count=count, access_rights_uid=access_rights_uid)
        return res
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = self.env.user.branch_ids.ids
            location_ids = self.env['stock.location'].search([
                ('branch_id', 'in', branch_ids),
                ('usage', '=', 'internal')
                ]).ids
            domain += [('location_id', 'in', location_ids)]
        return super(SerialLocations, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
