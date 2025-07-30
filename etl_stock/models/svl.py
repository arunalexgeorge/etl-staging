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
logger = logging.getLogger(__name__)
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime

class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'
    _order = 'create_date desc'
    
    @api.depends('product_id', 'product_id.categ_id', 'product_id.categ_id.category_type')
    def _compute_product_category(self):
        for valuation in self:
            categ = valuation.product_id.categ_id
            valuation.product_categ_id = categ.id
            valuation.category_type = categ.category_type
            valuation.fg_type = categ.fg_type and categ.fg_type or 'none' 
    
    def _compute_lot(self):
        for valuation in self:
            lot_ids = []
            if valuation.stock_move_id and valuation.stock_move_id.move_line_ids:
                lot_ids = [move_line.lot_id.id for move_line in valuation.stock_move_id.move_line_ids if move_line.lot_id]
            valuation.lot_ids = lot_ids
    
    @api.depends('remaining_qty', 'unit_cost')
    def _compute_rem_value(self):
        for valuation in self:
            valuation.remaining_value = round(valuation.remaining_qty * valuation.unit_cost, 2)
    
    @api.depends('stock_move_id', 'stock_move_id.location_id', 'stock_move_id.location_dest_id')
    def _compute_location(self):
        for svl in self:
            if svl.stock_move_id:
                svl.location_id = svl.stock_move_id.location_id.id
                svl.location_dest_id = svl.stock_move_id.location_dest_id.id
            else:
                svl.location_id = False
                svl.location_dest_id = False
    
    def _login_user(self):
        for serial in self:
            serial.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    def _sm_details(self):
        for svl in self:
            if svl.stock_move_id:
                svl.sm_id = str(svl.stock_move_id.id)
                svl.sm_qty = svl.stock_move_id.quantity_done
                svl.sml_ids = ','.join([str(sml.id) for sml in svl.stock_move_id.move_line_ids])
            else:
                svl.sm_id = ''
                svl.sm_qty = 0
                svl.sml_ids = ''
            svl.sml_id = svl.move_line_id and str(svl.move_line_id.id) or ''
                
    unit_cost = fields.Monetary('Unit Value', readonly=False)
    value = fields.Monetary('Total Value', readonly=False)
    quantity = fields.Float('Quantity', readonly=False, digits='Product Unit of Measure')
    up = fields.Float('Value(Correction)', digits='Product Unit of Measure')
    reference = fields.Char(related='stock_move_id.reference', store=True)
    category_type = fields.Selection([
        ('rm', 'RM'), 
        ('sfg', 'SFG'), 
        ('fg', 'FG'),
        ('scrap', 'Scrap'),
        ('service', 'Service'),
        ('none', 'None')
        ], 'Category Type', compute='_compute_product_category', store=True)
    fg_type = fields.Selection([
        ('pctr', 'PCTR'),
        ('ct', 'CT'),
        ('bg', 'BG'),
        ('bvc', 'BVC'),
        ('none', 'None')
        ], string='FG Type', compute='_compute_product_category', store=True)
    product_categ_id = fields.Many2one('product.category', 'Product Category', compute='_compute_product_category', store=True)
    remaining_qty = fields.Float(readonly=False, digits='Product Unit of Measure')
    remaining_quantity = fields.Float(readonly=False, digits='Product Unit of Measure')
    lot_ids = fields.Many2many('stock.lot', string='Lots', compute='_compute_lot')
    move_line_id = fields.Many2one('stock.move.line', 'Move Line')
    lot_id = fields.Many2one('stock.lot', 'Lot')
    remaining_value = fields.Float(compute='_compute_rem_value', store=True, digits='Product Unit of Measure')
    location_id = fields.Many2one('stock.location', 'Source', compute='_compute_location', store=True)
    location_dest_id = fields.Many2one('stock.location', 'Destination', compute='_compute_location', store=True)
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    sm_id = fields.Char('SM ID', compute='_sm_details')
    sm_qty = fields.Float('SM Qty', compute='_sm_details')
    sml_ids = fields.Char('SML IDs', compute='_sm_details')
    sml_id = fields.Char('SML ID', compute='_sm_details')
    create_date = fields.Datetime('Date')
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if not order:
            order = 'create_date DESC'
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            args += [('branch_id', 'in', branches_ids)]
        return super(StockValuationLayer, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            domain += [('branch_id', 'in', branches_ids)]
        result = super(StockValuationLayer, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=3000, orderby=orderby, lazy=lazy)
        for res in result:
            if 'value' in res:
                res['value'] = round(res['value'], 2)
        return result
    
    def delete_svl_sml_am(self):
        for svl in self:
         if not svl.lot_id:
            if svl.account_move_id:
                self._cr.execute('delete from account_move where id=%s'% (svl.account_move_id.id))
            if svl.move_line_id:
                self._cr.execute('delete from stock_move_line where id=%s'% (svl.move_line_id.id))
            self._cr.execute('delete from stock_valuation_layer where id=%s'% (svl.id))
        return True

    def update_sml_cost(self):
        for svl in self:
            if svl.up > 0 and svl.move_line_id:
                svl.move_line_id.unit_cost = svl.up
        return True
    
    def update_cost_correct_svl(self):
        for svl in self:
            svl.update_svl_value()
            svl.correct_svl_jv()
            svl.correct_to_smldate()
        return True
    
    def update_mrp_svl(self):
        for svl in self:
            if svl.stock_move_id and svl.stock_move_id.production_id:
                svl.stock_move_id.production_id.mrp_svl_correction()
        return True
    
    def update_svl_value(self):
        for svl in self:
            if 'IN' in svl.reference:
                branches = self.env['res.branch'].with_context(no_filter=True).search([])
                branches_dic = {}
                for branch in branches:
                    branches_dic.update({branch.code: branch.id})
                st_branch_id = svl.stock_move_id.st_branch_id
                if not st_branch_id:
                    st_branch_id = branches_dic.get(svl.reference.split('/')[0], st_branch_id)
                domain = [
                    ('quantity', '>', 0),
                    ('reference', '=', svl.reference),
                    ('product_id', '=', svl.product_id.id),
                    ('lot_id', '=', svl.lot_id.id),
                    ('branch_id', '=', st_branch_id),
                    ]
                branch_svls = self.with_context(no_filter=True).search(domain)
                unit_cost = branch_svls and branch_svls[0].unit_cost or 0.0
                svl.move_line_id.write({'unit_cost': unit_cost})
                svl.write({
                    'unit_cost': unit_cost,
                    'value': round(unit_cost * svl.quantity, 2) 
                    })
            else:
                domain = [
                    ('quantity', '>', 0),
                    ('product_id', '=', svl.product_id.id),
                    ('branch_id', '=', svl.branch_id.id),
                    ('create_date', '<', svl.move_line_id.date)
                    ]
                if svl.lot_id:
                    domain.append(('lot_id', '=', svl.lot_id.id))
                unit_cost = 0.0
                in_svls = self.search(domain, order='create_date desc')
                if in_svls:
                    if len(in_svls.ids) == 1:
                        unit_cost = in_svls[0].unit_cost
                    else:
                        domain = [
                            ('product_id', '=', svl.product_id.id),
                            ('branch_id', '=', svl.branch_id.id),
                            ('create_date', '<', svl.move_line_id.date),
                            ('id', '!=', svl.id)
                            ]
                        if svl.lot_id:
                            domain.append(('lot_id', '=', svl.lot_id.id))
                        all_svls = self.search(domain, order='create_date')
                        total_lot_cost, total_lot_qty = 0.0, 0.0
                        for all_svl in all_svls:
                            if all_svl.unit_cost > 0:
                                total_lot_cost += all_svl.value
                                total_lot_qty += all_svl.quantity
                        if total_lot_qty > 0:
                            unit_cost = round(total_lot_cost / total_lot_qty, 3)
                    svl.move_line_id.write({'unit_cost': unit_cost})
                    svl.write({
                        'unit_cost': unit_cost,
                        'value': round(unit_cost * svl.quantity, 2) 
                        })
            svl.correct_to_smldate()
        return True
    
    def update_remaining_qty(self, product_id, quantity, lot_id=False):
        domain = [
            ('quantity', '>', 0),
            ('remaining_qty', '>', 0),
            ('product_id', '=', product_id),
            ('branch_id', '=', self.branch_id.id)
            ]
        if lot_id:
            domain.append(('lot_id', '=', lot_id))
        svls = self.search(domain, order='create_date')
        rem_qty = quantity
        total_cost = 0.0
        for svl in svls:
            if rem_qty <= 0:
                break
            else:
                out_qty = round(min(svl.remaining_qty, rem_qty), 3)
                total_cost += round(out_qty * svl.unit_cost, 3)
                rem_svl_qty = round(svl.remaining_qty - out_qty, 3)
                svl.remaining_qty = rem_svl_qty 
                rem_qty = round(rem_qty - out_qty, 3)
        self.write({
            'unit_cost': round(total_cost / quantity, 3),
            'value': abs(total_cost) * -1 
            })
        return True
    
    def _validate_accounting_entries(self):
        am_vals = []
        for svl in self:
            if svl.product_id.valuation != 'real_time':
                continue
            if svl.product_id.categ_id.property_valuation == 'real_time':
                if svl.quantity < 0:
                    svl.update_svl_value()
                    svl.correct_to_smldate()
                am_vals += svl.stock_move_id._account_entry_move(svl.quantity, svl.description, svl.id, svl.value)
        if am_vals:
            account_moves = self.env['account.move'].sudo().create(am_vals)
            account_moves._post()
        date = self._context.get('force_date', False)
        if date:
            for svl in self:
                if svl.account_move_id:
                    self._cr.execute("""update account_move set date='%s' where id=%s"""% (date, svl.account_move_id.id))
                    for line in svl.account_move_id.line_ids:
                        self._cr.execute("""update account_move_line set date='%s' where id=%s"""% (date, line.id))
                if svl.stock_move_id:
                    self._cr.execute("""update stock_move set date='%s' where id=%s"""% (date, svl.stock_move_id.id))
                    self._cr.execute("""update stock_move_line set date='%s' where move_id=%s"""% (date, svl.stock_move_id.id))
                self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (date, svl.id))
                
    def update_move_line(self):
        total_count = len(self.ids)
        count = 1
        for svl in self:
            logger.info('%s/%s'%(count, total_count))
            count += 1
            if svl.stock_move_id:
                sign = 1
                if svl.quantity < 0.0:
                    sign = -1
                mls = svl.stock_move_id.move_line_ids
                if mls:
                    mls_count = len(mls.ids)
                    ml = mls[0]
                    if mls_count == 1:
                        svl.write({
                            'quantity': round(sign * ml.qty_done, 3),
                            'value': round(sign * ml.qty_done * svl.unit_cost, 2),
                            'move_line_id': ml.id,
                            'lot_id': ml.lot_id.id 
                            })
                        svl.correct_svl_jv()
                    else:
                        line_count = 1
                        for ml in mls:
                            if line_count == 1:
                                svl.write({
                                    'quantity': round(sign * ml.qty_done, 3),
                                    'value': round(sign * ml.qty_done * svl.unit_cost, 2),
                                    'move_line_id': ml.id,
                                    'lot_id': ml.lot_id.id 
                                    })
                                svl.correct_svl_jv()
                            else:
                                existing_vals = self.search([
                                    ('move_line_id', '=', ml.id)
                                    ])
                                if existing_vals:
                                    existing_vals.delete_svl_am()
                                new_svl = svl.copy({
                                    'quantity': round(sign * ml.qty_done, 3),
                                    'value': round(sign * ml.qty_done * svl.unit_cost, 2),
                                    'move_line_id': ml.id,
                                    'lot_id': ml.lot_id.id,
                                    'account_move_id': False,
                                    'branch_id': svl.branch_id.id
                                    })
                                new_svl.correct_svl_jv()
                                date = ml.date.strftime('%Y-%m-%d')
                                if new_svl.account_move_id:
                                    self._cr.execute("""update account_move set date='%s' where id=%s"""% (date, new_svl.account_move_id.id))
                                    for line in new_svl.account_move_id.line_ids:
                                        self._cr.execute("""update account_move_line set date='%s' where id=%s"""% (date, line.id))
                                self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (ml.date, new_svl.id))
                            line_count += 1
            else:
                if svl.quantity == 0:
                    svl.delete_svl_am()
                            
        return True
    
    def correct_costing_all(self):
        unit_cost_dic = {}
        company = self.env['res.company'].browse(1)
        file_data = company.read_csv_file()
        cost_dic = {}
        for data in file_data:
            cost_dic.update({data['Code']: data['Cost']})
        for product in self.env['product.product'].search([]):
            if product.default_code in cost_dic:
                unit_cost_dic.update({product.id: cost_dic[product.default_code]})
        for product_id in unit_cost_dic:
            self.correct_costing_ob(product_id, unit_cost_dic)
        return True
    
    def delete_svl_am(self):
        total_count = len(self.ids)
        count = 1
        for svl in self:
            logger.info('%s/%s'%(count, total_count))
            count += 1
            if svl.account_move_id:
                self._cr.execute('delete from account_move where id=%s'% (svl.account_move_id.id))
            self._cr.execute('delete from stock_valuation_layer where id=%s'% (svl.id))
        return True
    
    def delete_svl_data(self):
        return True
    
    def correct_svl_unitprice(self):
        return True
    
    def correct_svl_qtyvalue(self):
        return True
    
    def update_mo(self):
        for svl in self:
            if svl.stock_move_id and svl.stock_move_id.production_id:
                svl.stock_move_id.production_id.mrp_corrections()
        return True
    
    def update_mo_full(self):
        for svl in self:
            mos = []
            if svl.stock_move_id and svl.stock_move_id.production_id:
                mos.append(svl.stock_move_id.production_id.id)
            if mos:
                self.env['mrp.production'].browse(mos).mrp_corrections_full()
        return True
    
    def delete_svl_sm_am(self):
        for svl in self:
            if svl.account_move_id:
                self._cr.execute('delete from account_move where id=%s'% (svl.account_move_id.id))
            #if svl.stock_move_id:
            #   self._cr.execute('delete from stock_move_line where move_id=%s'% (svl.stock_move_id.id))
            #if svl.stock_move_id:
            #    self._cr.execute('delete from stock_move where id=%s'% (svl.stock_move_id.id))
            self._cr.execute('delete from stock_valuation_layer where id=%s'% (svl.id))
        return True
    
    def correct_uom(self):
        for svl in self:
            if svl.stock_move_id:
                self._cr.execute("""update stock_move set product_uom=1 where id=%s"""% (svl.stock_move_id.id))
                self._cr.execute("""update stock_move_line set product_uom_id=1 where move_id=%s"""% (svl.stock_move_id.id))
                self._cr.execute("""update product_template set uom_id=1 where id=%s"""% (svl.product_id.product_tmpl_id.id))
                self._cr.execute("""update product_template set uom_po_id=1 where id=%s"""% (svl.product_id.product_tmpl_id.id))
        return True
    
    def correct_ob_date(self):
        return True
    
    def correct_ob_date_oct(self):
        return True
    
    def correct_to_pickingdate(self):
        for svl in self:
            if svl.stock_move_id and svl.stock_move_id.picking_id:
                date = svl.stock_move_id.picking_id.date_done
                if svl.account_move_id:
                    self._cr.execute("""update account_move set date='%s' where id=%s"""% (date, svl.account_move_id.id))
                    for line in svl.account_move_id.line_ids:
                        self._cr.execute("""update account_move_line set date='%s' where id=%s"""% (date, line.id))
                if svl.stock_move_id:
                    self._cr.execute("""update stock_move set date='%s' where id=%s"""% (date, svl.stock_move_id.id))
                    self._cr.execute("""update stock_move_line set date='%s' where move_id=%s"""% (date, svl.stock_move_id.id))
                self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (date, svl.id))
        return True
    
    def correct_to_smldate(self):
        for svl in self:
            if svl.move_line_id:
                date = svl.move_line_id.date.strftime('%Y-%m-%d')
                if svl.account_move_id:
                    self._cr.execute("""update account_move set date='%s' where id=%s"""% (date, svl.account_move_id.id))
                    for line in svl.account_move_id.line_ids:
                        self._cr.execute("""update account_move_line set date='%s' where id=%s"""% (date, line.id))
                self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (svl.move_line_id.date, svl.id))
        return True
    
    def correct_to_movedate(self):
        for svl in self:
            if svl.stock_move_id:
                date = svl.stock_move_id.date.strftime('%Y-%m-%d')
                if svl.account_move_id:
                    self._cr.execute("""update account_move set date='%s' where id=%s"""% (date, svl.account_move_id.id))
                    for line in svl.account_move_id.line_ids:
                        self._cr.execute("""update account_move_line set date='%s' where id=%s"""% (date, line.id))
                self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (date, svl.id))
        return True
    
    def correct_jv_date(self):
        for svl in self:
            date = svl.create_date.strftime('%Y-%m-%d')
            date_time = svl.create_date.strftime('%Y-%m-%d %H:%M:%S')
            date = '2025-02-28'
            date_time = '2025-02-28 18:29:55'
            if svl.account_move_id:
                self._cr.execute("""update account_move set date='%s' where id=%s"""% (date, svl.account_move_id.id))
                for line in svl.account_move_id.line_ids:
                    self._cr.execute("""update account_move_line set date='%s' where id=%s"""% (date, line.id))
            if svl.stock_move_id:
                self._cr.execute("""update stock_move set date='%s' where id=%s"""% (date_time, svl.stock_move_id.id))
                self._cr.execute("""update stock_move_line set date='%s' where move_id=%s"""% (date_time, svl.stock_move_id.id))
            self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (date_time, svl.id))
        return True
    
    def correct_smsnl_date(self):
        for svl in self:
            date = svl.create_date.strftime('%Y-%m-%d %H:%M:%S')
            if svl.stock_move_id:
                self._cr.execute("""update stock_move set date='%s' where id=%s"""% (date, svl.stock_move_id.id))
                self._cr.execute("""update stock_move_line set date='%s' where move_id=%s"""% (date, svl.stock_move_id.id))
        return True
    
    def check_valuation_jv(self):
        total_debit, total_credit, total_value = 0.0, 0.0, 0.0
        for svl in self:
            if svl.account_move_id:
                debit = round(sum([line.debit for line in svl.account_move_id.line_ids]), 2)
                total_debit += debit
                credit = round(sum([line.credit for line in svl.account_move_id.line_ids]), 2)
                total_credit += credit
                total_value += round(svl.value, 2)
                logger.info('SVL ID: %s, JV#: %s, Debit: %s, Credit: %s, SVL Value: %s'%(svl.id, svl.account_move_id.name, debit, credit, svl.value))
                logger.info('-'*100)
        logger.info('*'*100)
        logger.info('Total JV Value:%s, Total SVL : %s'%(total_debit, total_value))
        logger.info('#'*100)
        return True
    
    def rm_zero(self):
        for svl in self:
            svl.remaining_qty = 0
        return True
    
    def rm_full(self):
        for svl in self:
            svl.remaining_qty = svl.quantity
        return True
    
    def correct_total_value(self):
        for svl in self:
            value = svl.value + svl.up
            svl.with_context(value=value).correct_svl_jv()
        return True
    
    def update_out_value(self):
        total_count = len(self.ids)
        count = 1
        for svl in self:
            logger.info('%s/%s'%(count, total_count))
            count += 1
            # svl.value = round(svl.quantity * svl.unit_cost, 2)
            # svl.correct_svl_jv()
            in_svls = self.search([
                ('product_id', '=', svl.product_id.id),
                ('lot_id', '=', svl.lot_id.id),
                ('quantity', '>', 0)
                ])
            # for in_svl in in_svls:
            #     in_svl.value = round(in_svl.quantity * in_svl.unit_cost, 2)
            #     in_svl.correct_svl_jv()
                
            total_value = abs(round(sum([round(svl.value, 3) for svl in in_svls]), 3))
            total_qty = round(sum([round(svl.quantity, 3) for svl in in_svls]), 3)
            unit_cost = round(total_value / total_qty, 3)
            out_svls = self.search([
                ('product_id', '=', svl.product_id.id),
                ('lot_id', '=', svl.lot_id.id),
                ('quantity', '<', 0)
                ])
            if out_svls:
                if len(out_svls.ids) == 1:
                    # total_value = round(out_svls[0].quantity*unit_cost, 2)
                    out_svls[0].unit_cost = unit_cost
                    out_svls[0].with_context(value=total_value*-1).correct_svl_jv()
                else:
                    for out_svl in out_svls:
                        out_svl.unit_cost = unit_cost
                        out_svl.correct_svl_jv()
        return True
    
    def update_total_value(self):
        for svl in self:
            svls = self.search([
                ('product_id', '=', svl.product_id.id),
                ('lot_id', '=', svl.lot_id.id),
                ('id', '!=', svl.id),
                ])
            total_value = abs(round(sum([round(svl.value, 3) for svl in svls]), 3))
            sign = 1
            if svl.quantity < 0:
                sign = -1
            total_value = round(sign * total_value, 2)
            svl.unit_cost = abs(round(total_value / svl.quantity, 3))
            svl.with_context(value=total_value).correct_svl_jv()
        return True
    
    def correct_svl_jv(self):
        count = 1
        total_count = len(self.ids)
        for svl in self:
            logger = logging.getLogger('SVL Update:')
            logger.info('%s/%s'%(count,total_count))
            count += 1
            if svl.move_line_id and svl.move_line_id.unit_cost > 0:
                svl.unit_cost = svl.move_line_id.unit_cost
            elif svl.unit_cost < 0:
                svl.unit_cost = abs(svl.unit_cost)
            # if svl.account_move_id:
            #     logger.info(svl.account_move_id.name)
            if 'value' in self._context:
                value = round(self._context['value'], 2)
            else:
                value = round(round(svl.quantity, 3) * round(abs(svl.unit_cost), 3), 2)
            svl.value = value
            if not svl.account_move_id:
                svl.with_context(value=value).create_svl_jv()
            move = svl.account_move_id
            product_account_id = svl.product_id.categ_id.property_stock_valuation_account_id.id
            stock_ctrl_acc_id = 5457
            for line in move.line_ids:
                self._cr.execute('update account_move_line set debit=0,credit=0,balance=0,amount_currency=0 where id=%s'%(line.id))
                # self._cr.execute('update account_move_line set credit=%s where id=%s'%(0, line.id))
                # self._cr.execute('update account_move_line set balance=%s where id=%s'%(0, line.id))
                # self._cr.execute('update account_move_line set amount_currency=%s where id=%s'%(0, line.id))
                if value < 0:
                    if line.account_id.id == stock_ctrl_acc_id:
                        self._cr.execute('update account_move_line set debit=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set balance=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set amount_currency=%s where id=%s'%(abs(value), line.id))
                    else:
                        self._cr.execute('update account_move_line set credit=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set balance=%s where id=%s'%(value, line.id))
                        self._cr.execute('update account_move_line set amount_currency=%s where id=%s'%(value, line.id))
                        self._cr.execute('update account_move_line set account_id=%s where id=%s'%(product_account_id, line.id))
                elif value > 0:
                    if line.account_id.id == stock_ctrl_acc_id:
                        self._cr.execute('update account_move_line set credit=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set balance=%s where id=%s'%(value, line.id))
                        self._cr.execute('update account_move_line set amount_currency=%s where id=%s'%(value, line.id))
                    else:
                        self._cr.execute('update account_move_line set debit=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set balance=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set amount_currency=%s where id=%s'%(abs(value), line.id))
                        self._cr.execute('update account_move_line set account_id=%s where id=%s'%(product_account_id, line.id))
            # svl.correct_jv_date()
            svl.correct_to_movedate()
        return True
    
    def create_svl_jv(self):
        for svl in self:
            if not svl.account_move_id:
                am_vals = []
                date = svl.create_date.strftime('%Y-%m-%d')
                if 'value' in self._context:
                    value = self._context['value']
                else:
                    value = round(round(svl.quantity, 3) * round(svl.unit_cost, 3), 2)
                svl.value = value
                am_vals = svl.stock_move_id.with_context(force_period_date=date)._account_entry_move(round(svl.quantity, 3), svl.description, svl.id, svl.value)
                if am_vals:
                    account_moves = self.env['account.move'].sudo().create(am_vals)
                    account_moves._post()
                    svl.account_move_id = account_moves.id
        return True
    
