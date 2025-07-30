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

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_repr, float_round, float_compare
from odoo.exceptions import ValidationError
from collections import defaultdict

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    def get_sml_lot_qty(self, branch_id, product_ids=[]):
        qty_dic = {}
        location_ids = self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('branch_id', '=', branch_id)
            ]).ids
        if not product_ids:
            product_ids = self.env['product.product'].search([]).ids
        in_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where 
                branch_id=%s AND
                location_dest_id in %s AND
                state='done' AND
                product_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(in_query, (branch_id, tuple(location_ids), tuple(product_ids)))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        prod_lots = []
        for qty_in in qtys_in:
            product = self.env['product.product'].browse(qty_in['product_id'])
            lot = self.env['stock.lot'].browse(qty_in['lot_id'])
            prod_lot = '%s_%s'%(str(product.default_code), str(lot.name))
            prod_lots.append(prod_lot)
            in_dic.update({prod_lot: round(qty_in['qty'], 3)})
        out_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where
                branch_id=%s AND
                location_id in %s AND
                state='done' AND
                product_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(out_query, (branch_id, tuple(location_ids), tuple(product_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            product = self.env['product.product'].browse(qty_out['product_id'])
            lot = self.env['stock.lot'].browse(qty_out['lot_id'])
            prod_lot = '%s_%s'%(str(product.default_code), str(lot.name))
            prod_lots.append(prod_lot)
            out_dic.update({prod_lot: round(qty_out['qty'], 3)})
        prod_lots = list(set(prod_lots))
        for prod_lot in prod_lots:
            qty_dic.update({prod_lot: round(in_dic.get(prod_lot, 0.0) - out_dic.get(prod_lot, 0.0), 3)})
        return qty_dic
    
    def get_svl_lot_qty(self, branch_id, product_ids=[]):
        if not product_ids:
            product_ids = self.env['product.product'].search([]).ids
        svl_query = """
            select product_id, lot_id, sum(quantity) as qty
            from stock_valuation_layer
            where branch_id=%s AND product_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(svl_query, (branch_id, tuple(product_ids)))
        qtys = self.env.cr.dictfetchall()
        svl_dic = {}
        prod_lots = []
        for svl in qtys:
            product = self.env['product.product'].browse(svl['product_id'])
            lot = self.env['stock.lot'].browse(svl['lot_id'])
            prod_lot = '%s_%s'%(str(product.default_code), str(lot.name))
            prod_lots.append(prod_lot)
            svl_dic.update({prod_lot: round(svl['qty'], 3)})
        return svl_dic 
    
    def get_prodloclot_qty_date(self, product_ids, location_id, date, lot_ids, branch_id):
        in_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where 
                branch_id=%s AND
                location_dest_id=%s AND
                date<=%s AND
                state='done' AND 
                product_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(in_query, (branch_id, location_id, date, tuple(product_ids)))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        prod_lots = []
        for qty_in in qtys_in:
            lot_id = qty_in['lot_id']
            if lot_id and lot_id != None:
                prod_lot = '%s_%s'%(str(qty_in['product_id']), str(lot_id))
            else:
                prod_lot = '%s_none'%(str(qty_in['product_id']))
            prod_lots.append(prod_lot)
            in_dic.update({prod_lot: round(qty_in['qty'], 3)})
        out_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where
                branch_id=%s AND
                location_id=%s AND
                date<=%s AND state='done' AND
                product_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(out_query, (branch_id, location_id, date, tuple(product_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            lot_id = qty_out['lot_id']
            if lot_id and lot_id != None:
                prod_lot = '%s_%s'%(str(qty_out['product_id']), str(lot_id))
            else:
                prod_lot = '%s_none'%(str(qty_out['product_id']))
            prod_lots.append(prod_lot)
            out_dic.update({prod_lot: round(qty_out['qty'], 3)})
        qty_dic = {}
        prod_lots = list(set(prod_lots))
        for prod_lot in prod_lots:
            qty_dic.update({prod_lot: round(in_dic.get(prod_lot, 0.0) - out_dic.get(prod_lot, 0.0), 3)})
        return qty_dic 
    
    def get_prodloclot_qty(self, product_ids, location_id, lot_ids, branch_id=False):
        if branch_id:
            branch_ids = [branch_id]
        else:
            branch_ids = self._context.get('allowed_branch_ids', [self.env.user.branch_id.id])
        in_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where location_dest_id=%s AND state='done'
                AND product_id in %s AND lot_id in %s
                AND branch_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(in_query, (location_id, tuple(product_ids), tuple(lot_ids), tuple(branch_ids)))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        prod_lots = []
        for qty_in in qtys_in:
            lot_id = qty_in['lot_id']
            if lot_id and lot_id != None:
                prod_lot = '%s_%s'%(str(qty_in['product_id']), str(lot_id))
            else:
                prod_lot = '%s_none'%(str(qty_in['product_id']))
            prod_lots.append(prod_lot)
            in_dic.update({prod_lot: round(qty_in['qty'], 3)})
        out_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where location_id=%s AND state='done'
                AND product_id in %s AND lot_id in %s
                AND branch_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(out_query, (location_id, tuple(product_ids), tuple(lot_ids), tuple(branch_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            lot_id = qty_out['lot_id']
            if lot_id and lot_id != None:
                prod_lot = '%s_%s'%(str(qty_out['product_id']), str(lot_id))
            else:
                prod_lot = '%s_none'%(str(qty_out['product_id']))
            prod_lots.append(prod_lot)
            out_dic.update({prod_lot: round(qty_out['qty'], 3)})
        qty_dic = {}
        prod_lots = list(set(prod_lots))
        for prod_lot in prod_lots:
            qty = in_dic.get(prod_lot, 0.0) - out_dic.get(prod_lot, 0.0)
            qty_dic.update({prod_lot: round(qty, 3)})
        return qty_dic 
    
    def get_prodcodeloclot_qty(self, product_ids, location_id, lot_ids, branch_id):
        if 'allowed_branch_ids' in self._context:
            branch_ids = self._context['allowed_branch_ids']
        else:
            branch_ids = self.env.user.branch_ids.ids 
        in_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where location_dest_id=%s AND state='done'
                AND product_id in %s AND lot_id in %s
                AND branch_id=%s
            group by product_id,lot_id;
            """
        self.env.cr.execute(in_query, (location_id, tuple(product_ids), tuple(lot_ids), branch_id))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        prod_lots = []
        for qty_in in qtys_in:
            product = self.env['product.product'].browse(qty_in['product_id'])
            lot = self.env['stock.lot'].browse(qty_in['lot_id'])
            prod_lot = '%s_%s'%(str(product.default_code), str(lot.name))
            prod_lots.append(prod_lot)
            in_dic.update({prod_lot: round(qty_in['qty'], 3)})
        out_query = """
            select product_id, lot_id, sum(qty_done) as qty
            from stock_move_line 
            where location_id=%s AND state='done'
                AND product_id in %s AND lot_id in %s
                AND branch_id in %s
            group by product_id,lot_id;
            """
        self.env.cr.execute(out_query, (location_id, tuple(product_ids), tuple(lot_ids), tuple(branch_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            product = self.env['product.product'].browse(qty_out['product_id'])
            lot = self.env['stock.lot'].browse(qty_out['lot_id'])
            prod_lot = '%s_%s'%(str(product.default_code), str(lot.name))
            prod_lots.append(prod_lot)
            out_dic.update({prod_lot: round(qty_out['qty'], 3)})
        qty_dic = {}
        prod_lots = list(set(prod_lots))
        for prod_lot in prod_lots:
            qty = in_dic.get(prod_lot, 0.0) - out_dic.get(prod_lot, 0.0)
            qty_dic.update({prod_lot: round(qty, 3)})
        return qty_dic  
    
    def _run_fifo_vacuum(self, company=None):
        return True
            
    def _prepare_in_svl_vals(self, quantity, unit_cost):
        self.ensure_one()
        value = round(unit_cost * quantity, 3)
        return {
            'product_id': self.id,
            'value': value,
            'unit_cost': unit_cost,
            'quantity': quantity,
            'remaining_quantity': quantity
            }
    
    def _prepare_out_svl_vals_custom(self, quantity, move_line):
        self.ensure_one()
        vals = {}
        if self.product_tmpl_id.cost_method == 'fifo':
            vals = self._run_fifo_out_custom(quantity, move_line)
        return vals
    
    def _run_fifo_out_custom(self, quantity, move_line):
        self.ensure_one()
        vals = {
            'quantity': -quantity,
            'move_line_id': move_line.id,
            }
        if move_line.lot_id:
            vals.update({'lot_id': move_line.lot_id.id})
        return vals
    
    def action_open_quants(self):
        quant_obj = self.env['stock.quant']
        self.ensure_one()
        locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        branch_ids = self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)
        numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        for location in locations:
            qtys_dic = self.get_prodloclot_qtys([self.id], [location.id])
            for qty_dic in qtys_dic:
                lot = qty_dic.split('_')[2]
                if lot:
                    lot_ok = True
                for i in lot:
                    if str(i) not in numbers:
                        lot_ok = False
                        break
                if lot and lot_ok:
                    lot_id = int(lot)
                else:
                    lot_id = False
                if qtys_dic[qty_dic] != 0:
                    domain = [
                        ('product_id', '=', self.id),
                        ('location_id', '=', location.id),
                        ('branch_id', 'in', branch_ids)
                        ]
                    if lot_id:
                        domain.append(('lot_id', '=', lot_id))
                    quants = quant_obj.search(domain)
                    if not quants:
                        quant_vals = {
                            'product_id': self.id,
                            'location_id': location.id,
                            'branch_id': location.branch_id.id
                            }
                        if lot_id:
                            quant_vals.update({'lot_id': lot_id})
                        new_quant = quant_obj.create(quant_vals)
        quants = quant_obj.search([
            ('product_id', '=', self.id),
            ('location_id.usage', '=', 'internal'),
            ('branch_id', 'in', branch_ids)
            ])
        quant_ids = []
        for quant in quants:
            if quant.quantity == 0 and quant.available_quantity == 0:
                quant_ids.append(quant.id)
        if quant_ids:
            if len(quant_ids) == 1:
                self._cr.execute('delete from stock_quant where id=%s'%quant_ids[0])
            else:
                self._cr.execute('delete from stock_quant where id in %s'%(tuple(quant_ids),))
        if len(self) == 1:
            self = self.with_context(default_product_id=self.id, single_product=True)
        else:
            self = self.with_context(product_tmpl_ids=self.product_tmpl_id.ids)
        action = quant_obj.action_view_inventory()
        action['domain'] = [('product_id', '=', self.id), ('location_id', 'in', locations.ids), ('branch_id', 'in', branch_ids)]
        action["name"] = 'Update Quantity'
        return action
    
    def get_prodqtys(self, product_ids, location_ids=[]):
        qty_dic = {}
        branch_ids = self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)
        if not location_ids:
            location_ids = self.env['stock.location'].search([
                ('branch_id', 'in', branch_ids), 
                ('usage', '=', 'internal')
                ]).ids
        if location_ids:
            if 'to_date' in self._context:
                in_query = """
                    select product_id,sum(qty_done) as qty
                    from stock_move_line 
                    where location_dest_id in %s AND state='done'
                        AND product_id in %s AND date<=%s AND branch_id in %s
                    group by product_id;
                    """
                self.env.cr.execute(in_query, (tuple(location_ids), tuple(product_ids), self._context['to_date'], tuple(branch_ids)))
            else: 
                in_query = """
                    select product_id,sum(qty_done) as qty
                    from stock_move_line 
                    where location_dest_id in %s AND state='done'
                        AND product_id in %s AND branch_id in %s
                    group by product_id;
                    """
                self.env.cr.execute(in_query, (tuple(location_ids), tuple(product_ids), tuple(branch_ids)))
            qtys_in = self.env.cr.dictfetchall()
            in_dic = {}
            for qty_in in qtys_in:
                in_dic.update({qty_in['product_id']: round(qty_in['qty'], 3)})
            if 'to_date' in self._context:
                out_query = """
                    select product_id,sum(qty_done) as qty
                    from stock_move_line 
                    where location_id in %s AND state='done'
                        AND product_id in %s AND date<=%s AND branch_id in %s
                    group by product_id;"""
                self.env.cr.execute(out_query, (tuple(location_ids), tuple(product_ids), self._context['to_date'], tuple(branch_ids)))
            else:
                out_query = """
                    select product_id,sum(qty_done) as qty
                    from stock_move_line 
                    where location_id in %s AND state='done'
                        AND product_id in %s AND branch_id in %s
                    group by product_id;
                    """
                self.env.cr.execute(out_query, (tuple(location_ids), tuple(product_ids), tuple(branch_ids)))
            qtys_out = self.env.cr.dictfetchall()
            out_dic = {}
            for qty_out in qtys_out:
                out_dic.update({qty_out['product_id']: round(qty_out['qty'], 3)})
            for product_id in product_ids:
                qty_dic.update({product_id: round(in_dic.get(product_id, 0.0) - out_dic.get(product_id, 0.0), 3)})
        return qty_dic
    
    def get_prodloclot_qtys(self, product_ids, location_ids):
        branch_ids = self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)
        in_query = """
            select product_id,location_dest_id,lot_id,sum(qty_done) as qty
            from stock_move_line 
            where location_dest_id=%s AND state='done'
                AND product_id in %s AND branch_id in %s
            group by product_id,location_dest_id,lot_id;
            """
        self.env.cr.execute(in_query, (tuple(location_ids), tuple(product_ids), tuple(branch_ids)))
        qtys_in = self.env.cr.dictfetchall()
        in_dic = {}
        prod_lots = []
        for qty_in in qtys_in:
            if qty_in['lot_id']:
                lot = str(qty_in['lot_id'])
            else:
                lot = 'none'
            prod_loc_lot = '%s_%s_%s'%(str(qty_in['product_id']), str(qty_in['location_dest_id']), lot)
            prod_lots.append(prod_loc_lot)
            in_dic.update({prod_loc_lot: round(qty_in['qty'], 3)})
        out_query = """
            select product_id,location_id,lot_id,sum(qty_done) as qty
            from stock_move_line 
            where location_id=%s AND state='done'
                AND product_id in %s AND branch_id in %s
            group by product_id,location_id,lot_id;
            """
        self.env.cr.execute(out_query, (tuple(location_ids), tuple(product_ids), tuple(branch_ids)))
        qtys_out = self.env.cr.dictfetchall()
        out_dic = {}
        for qty_out in qtys_out:
            if qty_out['lot_id']:
                lot = str(qty_out['lot_id'])
            else:
                lot = 'none'
            prod_loc_lot = '%s_%s_%s'%(str(qty_out['product_id']), str(qty_out['location_id']), lot)
            prod_lots.append(prod_loc_lot)
            out_dic.update({prod_loc_lot: round(qty_out['qty'], 3)})
        qty_dic = {}
        prod_lots = list(set(prod_lots))
        for prod_loc_lot in prod_lots:
            qty_dic.update({prod_loc_lot: round(in_dic.get(prod_loc_lot, 0.0) - out_dic.get(prod_loc_lot, 0.0), 3)})
        return qty_dic
    
    def _compute_quantities(self):
        products = self.filtered(lambda p: p.type != 'service')
        if products:
            res = self.get_prodqtys(products.ids)
        else:
            res = {}
        for product in products:
            product.qty_available = res.get(product.id, 0.0)
            product.incoming_qty = 0.0
            product.outgoing_qty = 0.0
            product.virtual_available = 0.0
            product.free_qty = 0.0
        # Services need to be set with 0.0 for all quantities
        services = self - products
        services.qty_available = 0.0
        services.incoming_qty = 0.0
        services.outgoing_qty = 0.0
        services.virtual_available = 0.0
        services.free_qty = 0.0
        
    qty_available = fields.Float('Quantity On Hand', compute='_compute_quantities', digits=(16,3))
    virtual_available = fields.Float('Forecasted Quantity', compute='_compute_quantities', digits=(16,3))
    free_qty = fields.Float('Free To Use Quantity ', compute='_compute_quantities', digits=(16,3))
    incoming_qty = fields.Float('Incoming', compute='_compute_quantities', digits=(16,3))
    outgoing_qty = fields.Float('Outgoing', compute='_compute_quantities', digits=(16,3))
    
    def _get_only_qty_available(self):
        currents = {}
        res = self.get_prodqtys(self.ids)
        for product in self:
            currents[product.id] = res.get(product.id, 0.0)
        return currents
    