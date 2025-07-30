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
import logging
logger = logging.getLogger(__name__)

class Lots(models.Model):
    _inherit = 'stock.lot'
    
    # @api.model
    # def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
    #     args = args or []
    #     if 'no_filter' in self._context:
    #         pass
    #     else:
    #         if 'allowed_branch_ids' in self._context:
    #             branch_ids = self._context['allowed_branch_ids']
    #         else:
    #             branch_ids = self.env.user.branch_ids.ids
    #         if branch_ids:
    #             location_ids = self.env['stock.location'].search([('branch_id', 'in', branch_ids)]).ids
    #             query = """
    #                 select lot_id
    #                 from stock_quant
    #                 where location_id in %s
    #                 """
    #             self.env.cr.execute(query, (tuple(location_ids),))
    #
    #             result = self.env.cr.dictfetchall()
    #             lot_ids = []
    #             for res in result:
    #                 lot_ids.append(res['lot_id'])
    #             lot_ids = list(set(lot_ids))
    #             args += [('id', 'in', lot_ids)]
    #
    #     return super(Lots, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    # @api.model
    # def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
    #     domain = domain or []
    #     if 'no_filter' in self._context:
    #         pass
    #     else:
    #         if 'allowed_branch_ids' in self._context:
    #             branch_ids = self._context['allowed_branch_ids']
    #         else:
    #             branch_ids = self.env.user.branch_ids.ids
    #         if branch_ids:
    #             location_ids = self.env['stock.location'].search([('branch_id', 'in', branch_ids)]).ids
    #             query = """
    #                 select lot_id
    #                 from stock_quant
    #                 where location_id in %s
    #                 """
    #             self.env.cr.execute(query, (tuple(location_ids),))
    #
    #             result = self.env.cr.dictfetchall()
    #             lot_ids = []
    #             for res in result:
    #                 lot_ids.append(res['lot_id'])
    #             lot_ids = list(set(lot_ids))
    #             domain += [('id', 'in', lot_ids)]
    #
    #     return super(Lots, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    def action_create_sl(self):
        for serial in self.serial_ids:
            serial.action_create_sl()
        return True
    
    def action_create_slall(self):
        lots = self.search([('categ_id', '=', self.categ_id.id)])
        for lot in lots:
            for serial in lot.serial_ids:
                serial.action_create_sl()
        return True
    
    @api.model
    def get_bag_qty(self, location_id):
        bag_qty = 0
        serial_ids = self.serial_ids.ids
        if serial_ids:
            in_query = """
                select serial_id,sum(quantity) as qty
                from stock_serial_line 
                where 
                    location_dest_id=%s and
                    serial_id in %s
                group by serial_id
                ;
                """
            self.env.cr.execute(in_query, (location_id, tuple(serial_ids)))
            in_result = self.env.cr.dictfetchall()
            in_dic = {}
            for sl_in in in_result:
                in_dic.update({sl_in['serial_id']: sl_in['qty']})
            out_query = """
                select serial_id,sum(quantity) as qty
                from stock_serial_line 
                where 
                    location_id=%s and
                    serial_id in %s
                group by serial_id
                ;
                """
            self.env.cr.execute(out_query, (location_id, tuple(serial_ids)))
            out_result = self.env.cr.dictfetchall()
            out_dic = {}
            for sl_out in out_result:
                out_dic.update({sl_out['serial_id']: sl_out['qty']})
            for serial_id in serial_ids:
                if round(in_dic.get(serial_id, 0.0), 3) !=  round(out_dic.get(serial_id, 0.0), 3):
                    bag_qty += 1
            # if out_result:
            #     out_list = []
            #     for sl_out in out_result:
            #         out_list.append(sl_out['serial_id'])
            #     for sl in in_dic:
            #         if sl not in out_list:
            #
            # else:
            #     bag_qty = len(in_result)
        return bag_qty
    
    def _compute_bag(self):
        for lot in self:
            bag_qty = 0
            location_ids = []
            for serial in lot.serial_ids:
                for line in serial.line_ids:
                    if line.location_dest_id.usage == 'internal':
                        location_ids.append(line.location_dest_id.id)
            location_ids = list(set(location_ids))
            for location_id in location_ids:
                bag_qty += lot.get_bag_qty(location_id)
            lot.bag_qty = bag_qty
    
    def _login_user(self):
        for lot in self:
            lot.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    def _product_qty(self):
        product_obj = self.env['product.product']
        product_ids = []
        lot_ids = []
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'), 
            ('branch_id', 'in', branch_ids)
            ])
        for lot in self:
            product_ids.append(lot.product_id.id)
            lot_ids.append(lot.id)
        for lot in self:
            product_qty = 0.0
            for location in locations:
                sml_qty_dic = product_obj.get_prodloclot_qty([lot.product_id.id], location.id, [lot.id])
                for prod_lot in sml_qty_dic:
                    product_qty += sml_qty_dic[prod_lot]
            lot.product_qty = round(product_qty, 3)
            serial_ids = [serial.id for serial in lot.serial_ids]
            sl_locs = self.env['stock.serial.location'].search([
                ('location_id', 'in', [loc.id for loc in locations]),
                ('serial_id', 'in', serial_ids)
                ])
            lot.sl_qty = round(sum(sl_locs.mapped('quantity')), 3)
    
    @api.depends('product_id', 'product_id.categ_id', 'product_id.categ_id.category_type')
    def _compute_categ(self):
        for lot in self:
            lot.categ_id = lot.product_id and lot.product_id.categ_id.id or False
            if lot.product_id.categ_id.category_type:
                category_type = lot.product_id.categ_id.category_type
            else:
                category_type = 'none'
            lot.category_type = category_type
            
    serial_ids = fields.One2many('stock.serial', 'lot_id', 'Serial Numbers')
    bag_qty = fields.Float('No. of Bags', compute='_compute_bag')
    update_qty = fields.Boolean()
    is_export = fields.Boolean('Is Export?')
    label_type = fields.Selection([
        ('local', 'Local'), 
        ('export', 'Export'), 
        ('export_us', 'Export(US)')
        ], 'Label Type', default='local')
    name = fields.Char('Lot Number', required=True, index='trigram')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    product_qty = fields.Float('Quantity', compute='_product_qty', digits=(16,3))
    sl_qty = fields.Float('SL Qty', compute='_product_qty', digits=(16,3))
    categ_id = fields.Many2one('product.category', 'Product Category', compute='_compute_categ', store=True)
    category_type = fields.Selection([
        ('rm', 'RM'), 
        ('sfg', 'SFG'), 
        ('fg', 'FG'),
        ('scrap', 'Scrap'),
        ('service', 'Service'),
        ('none', 'None')
        ], string='Category Type', 
        compute='_compute_categ', store=True)
    allow_sl_editing = fields.Boolean('Allow SL Editing', compute='_check_sl_access')
     
    def _check_sl_access(self):
        for lot in self:
            if self.user_has_groups('etl_base.group_sl_editing'):
                lot.allow_sl_editing = True
            else:
                lot.allow_sl_editing = False
                
    def action_print_label(self):
        if self.serial_ids:
            return self.env.ref('etl_stock.action_serial_number_label').report_action(self.serial_ids)
        else:
            return True
    
class StockMoveLines(models.Model):
    _inherit = 'stock.move.line'

    serial_id = fields.Many2one('stock.serial', 'Serial Number')
    lot_id = fields.Many2one('stock.lot', 'Lot Number',
        domain="[('product_id', '=', product_id), ('company_id', '=', company_id)]", check_company=True)
    lot_name = fields.Char('Lot Number Name')

