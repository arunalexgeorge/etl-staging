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
import pytz

class InventoryUpdation(models.Model):
    _name = 'inventory.updation'
    _description = 'Inventory Updation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'date'
    
    date = fields.Datetime('Date')
    location_id = fields.Many2one('stock.location', 'Location')
    branch_id = fields.Many2one('res.branch', 'Branch')
    data_file = fields.Binary('CSV File')
    data_file_name = fields.Char('File Name')
    stock_updated = fields.Boolean('Stock Updated', tracking=True)
    sn_updated = fields.Boolean('SerialNumber Updated', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'), 
        ('done', 'Done')
        ], 'Status', tracking=True, default='draft')
    categ = fields.Selection([('fg', 'FG'), ('others', 'Others')], 'Category')
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            args += [('branch_id', 'in', branches_ids)]
        return super(InventoryUpdation, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
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
        return super(InventoryUpdation, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    def read_csv_file(self):
        import_file = BytesIO(base64.decodebytes(self.data_file))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=',')
        return reader
    
    def check_reservation(self):
        products_dic = {}
        product_obj = self.env['product.product']
        quant_obj = self.env['stock.quant']
        products = product_obj.search([])
        for product in products:
            if product.default_code:
                products_dic.update({str(product.default_code): product})
        file_data = self.read_csv_file()
        missing_products = []
        product_list = []
        for data in file_data:
            if not 'Internal Reference' in data:
                raise UserError('Internal Reference column is missing')
            if not 'Lot Number' in data:
                raise UserError('Lot Number column is missing')
            if not 'Available Qty' in data:
                raise UserError('Available Qty column is missing')
            code = str(data['Internal Reference'])
            if code:
                product_list.append(code)
            if code and code not in products_dic:
                missing_products.append(code)
        if missing_products:
            raise UserError('Products missing in system : %s'%(missing_products))
        
        product_list = list(set(product_list))
        for product in product_list:
            quants = quant_obj.search([
                ('branch_id', '=', self.branch_id.id),
                ('location_id', '=', self.location_id.id),
                ('product_id', '=', products_dic[product].id)
                ])
            for quant in quants:
                if quant.reserved_quantity != 0:
                    raise UserError('Remove reservations for %s'%quant.product_id.default_code)
        return products_dic
    
    # def action_update_stock_old(self):
    #     products_dic = self.check_reservation()
    #     product_obj = self.env['product.product']
    #     quant_obj = self.env['stock.quant']
    #     lot_obj = self.env['stock.lot']
    #     file_data = self.read_csv_file()
    #     products_qty_dic = {}
    #     lot_list = []
    #     for data in file_data:
    #         if self.categ == 'fg':
    #             pass
    #         else:
    #             pass
    #         code = data['Internal Reference']
    #         if code:
    #             lot = data['Lot Number']
    #             qty = data['Available Qty']
    #             if qty:
    #                 qty = round(float(data['Available Qty']), 3)
    #             else:
    #                 raise UserError('Qty is missing for %s'%(code))
    #             product = products_dic[code]
    #             lots = lot_obj.search([
    #                 ('name', '=', lot), 
    #                 ('product_id', '=', product.id)
    #                 ])
    #             if lots:
    #                 lot_id = lots[0].id
    #             else:
    #                 lot_id = lot_obj.create({
    #                     'name': lot,
    #                     'product_id': product.id,
    #                     'company_id': 1
    #                     }).id
    #             if self.categ == 'fg':
    #                 lot_list.append(lot_id)
    #             else:
    #                 product_lot = '%s_%s'%(str(product.id),str(lot_id))
    #                 if product_lot in products_qty_dic:
    #                     products_qty_dic.update({product_lot: products_qty_dic[product_lot]+qty})
    #                 else:
    #                     products_qty_dic.update({product_lot: qty})
    #     lot_list = list(set(lot_list))
    #     if self.categ == 'fg':
    #         for lot_id in lot_list:
    #             lot = lot_obj.browse(lot_id)
    #             product_lot = '%s_%s'%(str(lot.product_id.id),str(lot_id))
    #             qty = 0
    #             for serial in lot.serial_ids:
    #                 qty += serial.get_location_qty(self.location_id.id)
    #             products_qty_dic.update({product_lot: qty})
    #
    #     for product_lot in products_qty_dic:
    #         product_id = int(product_lot.split('_')[0])
    #         product = product_obj.browse(product_id)
    #         lot_id = int(product_lot.split('_')[1])
    #         lot = lot_obj.browse(lot_id)
    #         product_quants = quant_obj.search([
    #             ('branch_id', '=', self.branch_id.id),
    #             ('location_id', '=', self.location_id.id),
    #             ('lot_id', '=', lot_id),
    #             ('product_id', '=', product_id),
    #             ])
    #         stock_qty = round(products_qty_dic[product_lot], 3)
    #         if product_quants:
    #             product_quant = product_quants[0]
    #             quant_av_qty = round(product_quant.available_quantity, 3)
    #             if quant_av_qty == stock_qty:
    #                 pass
    #             else:
    #                 product_quant.inventory_quantity = stock_qty
    #                 product_quant.with_context(force_date=self.date,
    #                     branch_id=self.branch_id.id).action_apply_inventory()
    #         else:
    #             product_quant = quant_obj.create({
    #                 'branch_id': self.branch_id.id,
    #                 'location_id': self.location_id.id,
    #                 'lot_id': lot_id,
    #                 'product_id': product_id
    #                 })
    #             product_quant.inventory_quantity = stock_qty
    #             product_quant.with_context(force_date=self.date, branch_id=self.branch_id.id).action_apply_inventory()
    #         lot.action_create_sl()
    #
    #     self.state = 'done'
    #     self.stock_updated = True
    #     return True
    
    def action_update_stock(self):
        products_dic = self.check_reservation()
        product_obj = self.env['product.product']
        quant_obj = self.env['stock.quant']
        lot_obj = self.env['stock.lot']
        file_data = self.read_csv_file()
        products_qty_dic = {}
        prod_lot_cost = {}
        lot_ids = []
        product_list = []
        ss_obj = self.env['stock.serial']
        for data in file_data:
            code = data['Internal Reference']
            if code:
                product_list.append(code)
                lot = data['Lot Number']
                qty = data['Available Qty']
                if 'Cost' in data and data['Cost']:
                    prod_lot = '%s_%s'%(code, lot)
                    prod_lot_cost.update({prod_lot: float(data['Cost'])})
                if qty:
                    qty = round(float(data['Available Qty']), 3)
                else:
                    raise UserError('Qty is missing for %s'%(code))
                product = products_dic[code]
                lots = lot_obj.search([
                    ('name', '=', lot), 
                    ('product_id', '=', product.id)
                    ])
                if lots:
                    lot_id = lots[0].id
                else:
                    lot_id = lot_obj.create({
                        'name': lot,
                        'product_id': product.id,
                        'company_id': 1
                        }).id
                if self.categ == 'fg':
                    pass
                else:
                    product_lot = '%s_%s'%(str(product.id),str(lot_id))
                    lot_ids.append(lot_id)
                    if product_lot in products_qty_dic:
                        products_qty_dic.update({product_lot: products_qty_dic[product_lot]+qty})
                    else:
                        products_qty_dic.update({product_lot: qty})
        product_list = list(set(product_list))
        product_ids = []
        for product in product_list:
            product_ids.append(products_dic[product].id)
        product_ids = list(set(product_ids))
        if self.categ == 'fg':
            in_dic = self.env['stock.serial.location'].get_qty_date(product_ids, self.location_id.id, self.date)
            serial_ids = [serial_id for serial_id in in_dic]
            for serial_id in serial_ids:
                serial = ss_obj.with_context(no_filter=True).browse(serial_id)
                product = serial.product_id
                qty = in_dic[serial_id]
                product_lot = '%s_%s'%(str(product.id),str(serial.lot_id.id))
                lot_ids.append(serial.lot_id.id)
                if product_lot in products_qty_dic:
                    products_qty_dic.update({product_lot: products_qty_dic[product_lot]+qty})
                else:
                    products_qty_dic.update({product_lot: qty})
        lot_ids = list(set(lot_ids))
        sml_qty_dic = product_obj.get_prodloclot_qty_date(product_ids, self.location_id.id, self.date, lot_ids, self.branch_id.id)
        current_date = fields.Datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        date_india = pytz.utc.localize(datetime.strptime(current_date, '%d-%m-%Y %H:%M:%S')).astimezone(pytz.timezone(('Asia/Calcutta')))
        current_date = date_india.strftime("%d-%m-%Y %H:%M:%S")
        inv_location_id = self.env.user.company_id.inv_location_id.id
        for product_lot in products_qty_dic:
            product_id = int(product_lot.split('_')[0])
            product_ids.append(product_id)
            product = product_obj.browse(product_id)
            lot_id = int(product_lot.split('_')[1])
            lot = lot_obj.browse(lot_id)
            product_lot_str = '%s_%s'%(product.default_code, lot.name)
            if product_lot in sml_qty_dic:
                if round(products_qty_dic[product_lot], 3) == round(sml_qty_dic[product_lot], 3):
                    pass
                else:
                    diff = round(products_qty_dic[product_lot], 3) - round(sml_qty_dic[product_lot], 3)
                    if diff > 0:
                        move_lines = [(0, 0, {
                            'location_id': inv_location_id, 
                            'location_dest_id': self.location_id.id,
                            'lot_id': lot_id,
                            'qty_done': diff,
                            'branch_id': self.branch_id.id,
                            'state': 'draft',
                            'product_id': product_id,
                            'product_uom_id': product.uom_id.id,
                            'reference': 'Inventory Updation : %s'%current_date,
                            'unit_cost': prod_lot_cost.get(product_lot_str, 0.0),
                            'date': self.date
                            })]
                        new_move = self.env['stock.move'].create({
                            'location_id': inv_location_id, 
                            'location_dest_id': self.location_id.id,
                            'branch_id': self.branch_id.id,
                            'quantity_done': diff,
                            'state': 'confirmed',
                            'product_id': product_id,
                            'product_uom': product.uom_id.id,
                            'product_uom_qty': diff,
                            'name': 'Inventory Updation : %s'%current_date,
                            'move_line_ids': move_lines,
                            'price_unit': prod_lot_cost.get(product_lot_str, 0.0),
                            'date': self.date
                            })
                        new_move.with_context(force_date=self.date)._action_done()
                    elif diff < 0:
                        move_lines = [(0, 0, {
                            'location_id': self.location_id.id, 
                            'location_dest_id': inv_location_id,
                            'lot_id': lot_id,
                            'qty_done': abs(diff),
                            'branch_id': self.branch_id.id,
                            'state': 'draft',
                            'product_id': product_id,
                            'product_uom_id': product.uom_id.id,
                            'reference': 'Inventory Updation : %s'%current_date,
                            'date': self.date
                            })]
                        new_move = self.env['stock.move'].create({
                            'location_id': self.location_id.id, 
                            'location_dest_id': inv_location_id,
                            'branch_id': self.branch_id.id,
                            'quantity_done': abs(diff),
                            'state': 'confirmed',
                            'product_id': product_id,
                            'product_uom': product.uom_id.id,
                            'product_uom_qty': abs(diff),
                            'name': 'Inventory Updation : %s'%current_date,
                            'move_line_ids': move_lines,
                            'date': self.date
                            })
                        new_move.with_context(force_date=self.date)._action_done()
            else:
                qty = round(products_qty_dic[product_lot], 3)
                move_lines = [(0, 0, {
                    'location_id': inv_location_id, 
                    'location_dest_id': self.location_id.id,
                    'lot_id': lot_id,
                    'qty_done': qty,
                    'branch_id': self.branch_id.id,
                    'state': 'draft',
                    'product_id': product_id,
                    'product_uom_id': product.uom_id.id,
                    'reference': 'Inventory Updation : %s'%current_date,
                    'unit_cost': prod_lot_cost.get(product_lot_str, 0.0),
                    'date': self.date
                    })]
                new_move = self.env['stock.move'].create({
                    'location_id': inv_location_id, 
                    'location_dest_id': self.location_id.id,
                    'branch_id': self.branch_id.id,
                    'quantity_done': qty,
                    'state': 'confirmed',
                    'product_id': product_id,
                    'product_uom': product.uom_id.id,
                    'product_uom_qty': qty,
                    'name': 'Inventory Updation : %s'%current_date,
                    'move_line_ids': move_lines,
                    'price_unit': prod_lot_cost.get(product_lot_str, 0.0),
                    'date': self.date
                    })
                new_move.with_context(force_date=self.date)._action_done()
        for product_lot in sml_qty_dic:
            qty = round(sml_qty_dic[product_lot], 3)
            if product_lot not in products_qty_dic:
                move_lines = [(0, 0, {
                    'location_id': self.location_id.id, 
                    'location_dest_id': inv_location_id,
                    'lot_id': lot_id,
                    'qty_done': qty,
                    'branch_id': self.branch_id.id,
                    'state': 'draft',
                    'product_id': product_id,
                    'product_uom_id': product.uom_id.id,
                    'reference': 'Inventory Updation : %s'%current_date,
                    'date': self.date
                    })]
                new_move = self.env['stock.move'].create({
                    'location_id': self.location_id.id, 
                    'location_dest_id': inv_location_id,
                    'branch_id': self.branch_id.id,
                    'quantity_done': qty,
                    'state': 'confirmed',
                    'product_id': product_id,
                    'product_uom': product.uom_id.id,
                    'product_uom_qty': qty,
                    'name': 'Inventory Updation : %s'%current_date,
                    'move_line_ids': move_lines,
                    'date': self.date
                    })
                new_move.with_context(force_date=self.date)._action_done()
        sml_qty_curr_dic = product_obj.get_prodloclot_qty_date(product_ids, self.location_id.id, self.date, lot_ids, self.branch_id.id)
        actual_product_lots = []
        for product_lot in sml_qty_curr_dic:
            actual_product_lots.append(product_lot)
            product_id = int(product_lot.split('_')[0])
            product_ids.append(product_id)
            product = product_obj.browse(product_id)
            lot_str = product_lot.split('_')[1]
            lot_id = False
            if lot_str != 'none':
                lot_id = int(lot_str)
            qty = round(sml_qty_curr_dic[product_lot], 3)
            quant_domain = [
                ('branch_id', '=', self.branch_id.id),
                ('location_id', '=', self.location_id.id),
                ('product_id', '=', product_id)]
            if lot_id:
                quant_domain.append(('lot_id', '=', lot_id))
            product_quants = quant_obj.search(quant_domain)
            if not product_quants:
                quant_vals = {
                    'branch_id': self.branch_id.id,
                    'location_id': self.location_id.id,
                    'product_id': product_id,
                    }
                if lot_id:
                    quant_vals.update({'lot_id': lot_id})
                quant_obj.create(quant_vals)
        self.state = 'done'
        self.stock_updated = True
        return True
    
    def action_update_sn(self):
        products_dic = self.check_reservation()
        lot_obj = self.env['stock.lot']
        file_data = self.read_csv_file()
        sn_list = []
        product_list = []
        sl_obj = self.env['stock.serial.location']
        ss_obj = self.env['stock.serial']
        ssl_obj = self.env['stock.serial.line']
        for data in file_data:
            code = data['Internal Reference']
            if code:
                product_list.append(code)
                if not 'Serial Number' in data:
                    raise UserError('Serial Number column is missing')
                if not data['Serial Number']:
                    raise UserError('Serial Number is missing for %s'%(data['Internal Reference']))
                sl_no = data['Serial Number'].replace('\n', '').replace(' ', '')
                if sl_no in sn_list:
                    raise UserError('Serial Number %s is duplicated'%(sl_no))
                else:
                    sn_list.append(sl_no)
                if not 'Manufacturing Date' in data:
                    raise UserError('Manufacturing Date column is missing')
                if not data['Manufacturing Date']:
                    raise UserError('Manufacturing Date is missing for %s'%(data['Internal Reference']))
        
        product_list = list(set(product_list))
        product_ids = []
        for product in product_list:
            product_ids.append(products_dic[product].id)
        existing_locs = sl_obj.with_context(no_filter=True).search([
            ('location_id', '=', self.location_id.id),
            ('branch_id', '=', self.branch_id.id),
            ('product_id', 'in', product_ids)
            ])
        existing_lots = []
        for loc in existing_locs:
            existing_lots.append(loc.lot_id)
        existing_lots = list(set(existing_lots))
        # for lot in existing_lots:
        #     lot.action_create_sl()
        existing_locs = sl_obj.with_context(no_filter=True).search([
            ('location_id', '=', self.location_id.id),
            ('branch_id', '=', self.branch_id.id),
            ('product_id', 'in', product_ids)
            ])
        file_data2 = self.read_csv_file()
        inv_location_id = self.env['res.company'].browse(1).inv_location_id.id
        actual_sns = {}
        line_count = 1
        actual_sn_ids = []
        for data in file_data2:
            # if line_count >= 158:
            #     continue
            code = data['Internal Reference']
            lot = data['Lot Number']
            qty = round(float(data['Available Qty']), 3)
            product = products_dic[code]
            if code:
                sl_no = data['Serial Number'].replace('\n', '').replace(' ', '')
                actual_sns.update({'%s_%s_%s'%(sl_no,code,lot): qty})
                mfg_date = datetime.strptime(data['Manufacturing Date'], "%d-%m-%Y").strftime('%Y-%m-%d')
                prod_lots = lot_obj.search([
                    ('name', '=', lot), 
                    ('product_id', '=', product.id)
                    ])
                if prod_lots:
                    lot_id = prod_lots[0].id
                else:
                    lot_id = lot_obj.create({
                        'name': lot,
                        'product_id': product.id,
                        'company_id': 1
                        }).id
                if lot_id:
                    sl_vals = {
                        'name': sl_no,
                        'lot_id': lot_id,
                        'date': mfg_date,
                        }
                    serial_numbers = ss_obj.with_context(no_filter=True).search([
                        ('name', '=', sl_no), 
                        ('lot_id', '=', lot_id)
                        ])
                    if serial_numbers:
                        sl = serial_numbers[0]
                        actual_sn_ids.append(sl.id)
                        sl_qty = round(sl.get_location_qtydate(self.location_id.id, self.date), 3)
                        if qty == sl_qty:
                            pass
                            # sl.action_create_sl()
                        else:
                            diff = round(qty - sl_qty, 3)
                            if diff > 0:
                                ssl_vals = {
                                    'serial_id': sl.id,
                                    'location_id': inv_location_id,
                                    'location_dest_id': self.location_id.id,
                                    'quantity': diff,
                                    'date': self.date
                                    }
                            elif diff < 0:
                                ssl_vals = {
                                    'serial_id': sl.id,
                                    'location_id': self.location_id.id,
                                    'location_dest_id': inv_location_id,
                                    'quantity': diff*-1,
                                    'date': self.date
                                    }
                            if 'Loose Stock' in data and data['Loose Stock'] == 'YES':
                                sl_vals.update({
                                    'initial_qty_manual': sl.product_id.weight_bag, 
                                    'loose_stock': True
                                    })
                            ssl_obj.create(ssl_vals)
                            sl.action_create_sl()
                    else:
                        if 'Loose Stock' in data and data['Loose Stock'] == 'YES':
                            sl_vals.update({
                                'initial_qty_manual': product.weight_bag, 
                                'loose_stock': True
                                })
                        sl = ss_obj.create(sl_vals)
                        actual_sn_ids.append(sl.id)
                        ssl_vals = {
                            'serial_id': sl.id,
                            'location_id': inv_location_id,
                            'location_dest_id': self.location_id.id,
                            'quantity': qty,
                            'date': self.date,
                            }
                        ssl_obj.create(ssl_vals)
                        sl.action_create_sl()
            line_count += 1
        
        in_dic = self.env['stock.serial.location'].get_qty_date(product_ids, self.location_id.id, self.date)
        serial_ids = [serial_id for serial_id in in_dic]
        serial_ids = list(set(serial_ids))
        for serial_id in serial_ids:
            if serial_id not in actual_sn_ids:
                serial = ss_obj.browse(serial_id)
                serial.action_zero_location_date(self.location_id.id, self.date)
        self.sn_updated = True
        return True
