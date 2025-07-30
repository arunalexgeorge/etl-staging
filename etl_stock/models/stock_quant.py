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
import logging
from asyncio.base_events import ssl
logger = logging.getLogger("_update_reserved_quantity:")
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime
import pytz

class StockQuant(models.Model):
    _inherit = 'stock.quant'
    
    def action_product_lot_location_zero(self):
        inv_location_id = self.env.user.company_id.inv_location_id.id
        current_date = fields.Datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        date_india = pytz.utc.localize(datetime.strptime(current_date, '%d-%m-%Y %H:%M:%S')).astimezone(pytz.timezone(('Asia/Calcutta')))
        current_date = date_india.strftime("%d-%m-%Y %H:%M:%S")
        for quant in self:
            if quant.quantity == 0:
                continue
            elif quant.quantity > 0:
                location_id = quant.location_id.id
                location_dest_id = inv_location_id
            elif quant.quantity < 0:
                location_id = inv_location_id
                location_dest_id = quant.location_id.id
            move_lines = [(0, 0, {
            'location_id': location_id, 
            'location_dest_id': location_dest_id,
            'branch_id': quant.branch_id.id,
            'lot_id': quant.lot_id.id,
            'qty_done': abs(quant.quantity),
            'state': 'draft',
            'product_id': quant.product_id.id,
            'product_uom_id': quant.product_id.uom_id.id,
            'reference': 'Inventory Updation : %s'%current_date,
            })]
            new_move = self.env['stock.move'].create({
                'location_id': location_id, 
                'location_dest_id': location_dest_id,
                'branch_id': quant.branch_id.id,
                'quantity_done': abs(quant.quantity),
                'state': 'confirmed',
                'product_id': quant.product_id.id,
                'product_uom': quant.product_id.uom_id.id,
                'product_uom_qty': abs(quant.quantity),
                'name': 'Inventory Updation : %s'%current_date,
                'move_line_ids': move_lines,
                })
            new_move._action_done()
        return True
    
    def get_prodloclot_qty(self, product_ids, location_id):
        product_quants = self.search([
            ('location_id', '=', location_id),
            ('product_id', 'in', product_ids),
            ])
        qty_dic = {}
        for quant in product_quants:
            prod_lot = '%s_%s'%(str(quant.product_id.id), str(quant.lot_id.id))
            qty_dic.update({prod_lot: round(quant.available_quantity, 3)})
        return qty_dic  
    
    def action_inventory_history(self):
        self.ensure_one()
        domain = [
                '|',
                ('location_id', '=', self.location_id.id),
                ('location_dest_id', '=', self.location_id.id)
                ]
        if self.lot_id:
            domain.append(('lot_id', '=', self.lot_id.id))
        action = {
            'name': _('History'),
            'view_mode': 'list,form',
            'res_model': 'stock.move.line',
            'views': [(self.env.ref('stock.view_move_line_tree').id, 'list'), (False, 'form')],
            'type': 'ir.actions.act_window',
            'context': {
                'search_default_done': 1,
                'search_default_product_id': self.product_id.id,
                },
            'domain': domain,
            }
        return action
    
    def update_svl_remaining_qtys(self):
        
        return True
    
    def update_svl_remaining_qty(self):
        for quant in self:
            svls = self.env['stock.valuation.layer'].search([
                ('product_id', '=', quant.product_id.id),
                ('lot_id', '=', quant.lot_id.id),
                ('quantity', '>', 0),
                ('branch_id', '=', quant.branch_id.id),
                ], order='create_date desc')
            total_qty = 0
            lot_quants = self.search([
                ('lot_id', '=', quant.lot_id.id),
                ('branch_id', '=', quant.branch_id.id),
                ('location_id.usage', '=', 'internal')
                ])
            rem_qty = round(sum([q.quantity for q in lot_quants]), 3)
            for svl in svls:
                if total_qty == round(quant.quantity, 3):
                    svl.remaining_qty = 0
                else:
                    svl_qty = round(svl.quantity, 3)
                    if svl_qty >= rem_qty:
                        svl.remaining_qty = rem_qty
                        rem_qty = 0
                        total_qty = round(total_qty + svl_qty, 3)
                    else:
                        total_qty = round(total_qty + min(svl_qty, rem_qty), 3)
                        svl.remaining_qty = svl_qty
                        rem_qty = round(rem_qty - svl_qty, 3)
        return True
    
    @api.model
    def _update_reserved_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None, strict=False):
        return []
    
    @api.depends('product_id', 'product_id.categ_id', 'product_id.categ_id.category_type', 'product_id.default_code')
    def _compute_product_details(self):
        for quant in self:
            product_code = ''
            quant.product_categ_id = quant.product_id.categ_id.id
            if quant.product_id.categ_id.category_type:
                category_type = quant.product_id.categ_id.category_type
            else:
                category_type = 'none'
            quant.category_type = category_type
            if quant.product_id:
                product_code = quant.product_id.default_code
            quant.product_code = product_code
    
    def _compute_bag(self):
        for quant in self:
            if quant.lot_id and quant.location_id.usage == 'internal':
                quant.bag_qty = quant.lot_id.get_bag_qty(quant.location_id.id)
            else:
                quant.bag_qty = 0
    
    @api.depends('product_id', 'product_id.default_code')
    def _compute_product_code(self):
        for quant in self:
            product_code = ''
            if quant.product_id:
                product_code = quant.product_id.default_code
            quant.product_code = product_code
    
    def _domain_lot_id(self):
        if not self._is_inventory_mode():
            return
        domain = [
            "'|'",
                "('company_id', '=', company_id)",
                "('company_id', '=', False)"]
        if self.env.context.get('active_model') == 'product.product':
            domain.insert(0, "('product_id', '=', %s)" % self.env.context.get('active_id'))
        elif self.env.context.get('active_model') == 'product.template':
            product_template = self.env['product.template'].browse(self.env.context.get('active_id'))
            if product_template.exists():
                domain.insert(0, "('product_id', 'in', %s)" % product_template.product_variant_ids.ids)
        else:
            domain.insert(0, "('product_id', '=', product_id)")
        return '[' + ', '.join(domain) + ']'
    
    def _compute_quantities(self):
        qty_dic = self.get_res_qty()
        for quant in self:
            reserved_quantity, done_quantity = 0.0, 0.0
            if quant.location_id.usage == 'internal':
                if quant.product_id and quant.location_id:
                    lot = quant.lot_id and str(quant.lot_id.id) or 'none'
                    quant_key = '%s_%s_%s'%(str(quant.product_id.id), str(quant.location_id.id), lot)
                    reserved_quantity = qty_dic[0].get(quant_key, 0.0)
                    done_quantity = qty_dic[1].get(quant_key, 0.0) - qty_dic[2].get(quant_key, 0.0)
            quant.quantity = done_quantity
            quant.reserved_quantity = reserved_quantity
            quant.available_quantity = done_quantity - reserved_quantity
    
    def _login_user(self):
        for quant in self:
            quant.login_user_id = self.env.user.user_access and self.env.user.id or False
            
    bag_qty = fields.Float('No. of Bags', compute='_compute_bag')
    product_categ_id = fields.Many2one('product.category', compute='_compute_product_details', store=True)
    category_type = fields.Selection([
        ('rm', 'RM'), 
        ('sfg', 'SFG'), 
        ('fg', 'FG'),
        ('scrap', 'Scrap'),
        ('service', 'Service'),
        ('none', 'None')
        ], string='Category Type', 
        compute='_compute_product_details', store=True)
    reserved_quantity = fields.Float('Reserved Quantity', compute='_compute_quantities', digits='Product Unit of Measure')
    quantity = fields.Float('On Hand Quantity', compute='_compute_quantities', digits='Product Unit of Measure')
    available_quantity = fields.Float('Available Quantity', compute='_compute_quantities', digits='Product Unit of Measure')
    product_code = fields.Char('Internal Reference', compute='_compute_product_details', store=True)
    lot_id = fields.Many2one('stock.lot', 'Lot Number', index=True, ondelete='restrict', check_company=True,
        domain=lambda self: self._domain_lot_id()) 
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    
    def get_res_qty(self):
        product_ids, loc_ids = [], []
        for quant in self:
            if quant.location_id.usage == 'internal':
                product_ids.append(quant.product_id.id)
                loc_ids.append(quant.location_id.id)
        product_ids = list(set(product_ids))
        loc_ids = list(set(loc_ids))
        res_dic = {}
        done_in_dic = {}
        done_out_dic = {}
        branch_ids = self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)
        if product_ids:
            query_res = """
                select product_id,location_id,lot_id,sum(reserved_uom_qty) as res_qty
                from stock_move_line 
                where 
                    product_id in %s and state not in ('cancel','done')
                    and location_id in %s and branch_id in %s
                group by product_id,location_id,lot_id
                ;
                """
            self.env.cr.execute(query_res, (tuple(product_ids), tuple(loc_ids), tuple(branch_ids)))
            reserved_result = self.env.cr.dictfetchall()
            
            query_in = """
                select product_id,location_dest_id,lot_id,sum(qty_done) as done_qty
                from stock_move_line 
                where 
                    product_id in %s and state='done'
                    and location_dest_id in %s and branch_id in %s
                group by product_id,location_dest_id,lot_id
                ;
                """
            self.env.cr.execute(query_in, (tuple(product_ids), tuple(loc_ids), tuple(branch_ids)))
            result_in = self.env.cr.dictfetchall()
            query_out = """
                select product_id,location_id,lot_id,sum(qty_done) as done_qty
                from stock_move_line 
                where 
                    product_id in %s and state='done'
                    and location_id in %s and branch_id in %s
                group by product_id,location_id,lot_id
                ;
                """
            self.env.cr.execute(query_out, (tuple(product_ids), tuple(loc_ids), tuple(branch_ids)))
            result_out = self.env.cr.dictfetchall()
                
            for res in result_in:
                if res['lot_id'] and res['lot_id'] != None:
                    lot = str(res['lot_id'])
                else:
                    lot = 'none'
                quant_key = '%s_%s_%s'%(str(res['product_id']), str(res['location_dest_id']), lot)
                done_in_dic.update({quant_key: res['done_qty']})
            for res in result_out:
                if res['lot_id'] and res['lot_id'] != None:
                    lot = str(res['lot_id'])
                else:
                    lot = 'none'
                quant_key = '%s_%s_%s'%(str(res['product_id']), str(res['location_id']), lot)
                done_out_dic.update({quant_key: res['done_qty']})
            for res in reserved_result:
                quant_key = '%s_%s_%s'%(str(res['product_id']), str(res['location_id']), str(res.get('lot_id', 'no_lot')))
                res_dic.update({quant_key: res['res_qty']})
        return [res_dic, done_in_dic, done_out_dic]
    
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """ Override to set the `inventory_quantity` field if we're in "inventory mode" as well
        as to compute the sum of the `available_quantity` field.
        """
        if 'available_quantity' in fields:
            if 'quantity' not in fields:
                fields.append('quantity')
            if 'reserved_quantity' not in fields:
                fields.append('reserved_quantity')
        if 'inventory_quantity_auto_apply' in fields and 'quantity' not in fields:
            fields.append('quantity')
        result = super(StockQuant, self).read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        for group in result:
            if self.env.context.get('inventory_report_mode'):
                group['inventory_quantity'] = False
            if group.get('__domain'):
                quants = self.search(group['__domain'])
                available_quantity, quantity, reserved_quantity = 0.0, 0.0, 0.0
                for quant in quants:
                    available_quantity += quant.available_quantity
                    quantity += quant.quantity
                    reserved_quantity += quant.reserved_quantity
                group['available_quantity'] = available_quantity
                group['quantity'] = quantity
                group['reserved_quantity'] = reserved_quantity
                if 'inventory_quantity_auto_apply' in fields:
                    group['inventory_quantity_auto_apply'] = quantity
        return result