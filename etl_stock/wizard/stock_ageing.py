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

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang, xlwt
from io import BytesIO
import base64
from datetime import datetime, timedelta

class StockAgeing(models.TransientModel):
    _name = 'stock.ageing'
    _description = 'Stock Ageing' 

    date = fields.Date('As on')
    categ_ids = fields.Many2many('product.category', string='Categories')
    location_ids = fields.Many2many('stock.location', string='Locations')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    branch_ids = fields.Many2many('res.branch', string='Branches', required=True)
    
    @api.model
    def default_get(self, default_fields):
        res = super(StockAgeing, self).default_get(default_fields)
        res.update({'branch_ids' : self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)})
        return res
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Stock Ageing Report')
        title_centre = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_left_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz left, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_blank = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_300 = xlwt.easyxf('font: height 300, name Arial, colour_index black, bold on; align: horiz centre, vert centre;border: bottom thin, top thin, left thin, right thin')
        title_left = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz left;')
        string_left = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz left;')
        string_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;')
        number_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;',num_format_str='#,##0;-#,##0')
        string_left_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz left;')
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin, top thin; align: horiz right;',num_format_str='#,##0.000;-#,##0.000')
        number2d_bold_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on;border: bottom thin, top thin, left thin, right thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.000;-#,##0.000')
        number0d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;; align: horiz right;',num_format_str='###0;###0')
        number0d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='###0;###0')
        for i in range(0, 15):
            ws.col(i).width = 4000
        ws.col(2).width = 8000
        ws.write_merge(0, 1, 0, 6, 'Stock Ageing Report', title_centre_300)
        date = 'As on: ' + self.date.strftime('%d-%m-%Y') 
        ws.write_merge(2, 3, 0, 6, date, title_left)
        prod_obj = self.env['product.product']
        lot_obj = self.env['stock.lot']
        svl_obj = self.env['stock.valuation.layer']
        quant_obj = self.env['stock.quant']
        if self.location_ids:
            locations = self.location_ids
        else:
            locations = self.env['stock.location'].search([
                ('usage', '=', 'internal')
                ])
        col = 4
        serial_loc_obj = self.env['stock.serial.line']
        to_date = datetime.strptime(self.date.strftime('%Y-%m-%d 23:59:59'), "%Y-%m-%d %H:%M:%S")
        next_date = self.date + timedelta(days=1)
        total_value = 0.0
        total_quantity = 0.0
        for location in locations:
            total_qty = 0
            loc_prod_dic = {}
            for categ in self.categ_ids:
                domain = [
                    ('categ_id', '=', categ.id), 
                    ('type', '!=', 'detailed_service')
                    ]
                product_ids = prod_obj.search(domain, order='name').ids
                if product_ids:
                    svl_query = """SELECT distinct(svl.product_id),sum(svl.quantity) as qty,sum(svl.value) as value
                        FROM stock_valuation_layer svl
                        WHERE 
                            svl.product_id IN %s
                            AND svl.create_date < %s
                            AND svl.branch_id in %s
                        GROUP BY
                            svl.product_id
                        """
                    branch_ids = self.branch_ids.ids
                    self.env.cr.execute(svl_query, (tuple(product_ids), next_date, tuple(branch_ids)))
                    svl_res = self.env.cr.dictfetchall()
                    prod_up_dic = {}
                    for res in svl_res:
                        if res['qty'] > 0:
                            prod_up_dic.update({res['product_id']: round(res['value'] / res['qty'], 3)})
                    if categ.category_type == 'fg':
                        ssls = serial_loc_obj.search([
                            ('product_id', 'in', product_ids),
                            '|',
                            ('location_id', '=', location.id),
                            ('location_dest_id', '=', location.id),
                            ('serial_id.date', '<', next_date),
                            ('date', '<', next_date),
                            ])
                        act_prod_ids = []
                        for ssl in ssls:
                            act_prod_ids.append(ssl.serial_id.product_id.id)
                        act_prod_ids = list(set(act_prod_ids))
                        product_ids = prod_obj.search([('id', 'in', act_prod_ids)], order='default_code').ids
                        for product_id in product_ids:
                            product = prod_obj.browse(product_id)
                            qty, qty_030, qty_3060, qty_6090, qty_90120, qty_120 = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                            ssls = serial_loc_obj.with_context(no_filter=True).search([
                                ('product_id', '=', product_id),
                                '|',
                                ('location_id', '=', location.id),
                                ('location_dest_id', '=', location.id),
                                ('serial_id.date', '<', next_date),
                                ('date', '<', next_date),
                                ])
                            serials = []
                            for ssl in ssls:
                                serials.append(ssl.serial_id)
                            serials = list(set(serials))
                            for serial in serials:
                                serials_in = serial_loc_obj.search([
                                    ('product_id', '=', product_id),
                                    ('location_dest_id', '=', location.id),
                                    ('date', '<', next_date),
                                    ('serial_id', '=', serial.id)
                                    ])
                                qty_in = round(sum([serials_in.quantity for serials_in in serials_in]), 3)
                                serials_out = serial_loc_obj.search([
                                    ('product_id', '=', product_id),
                                    ('location_id', '=', location.id),
                                    ('date', '<', next_date),
                                    ('serial_id', '=', serial.id)
                                    ])
                                qty_out = round(sum([serials_out.quantity for serials_out in serials_out]), 3)
                                sl_qty = round(qty_in - qty_out, 3)
                                if sl_qty > 0: 
                                    qty += sl_qty
                                    diff = (self.date - serial.date).days
                                    if diff <= 30:
                                        qty_030 += sl_qty
                                    elif diff <= 60:
                                        qty_3060 += sl_qty
                                    elif diff <= 90:
                                        qty_6090 += sl_qty
                                    elif diff <= 120:
                                        qty_90120 += sl_qty
                                    else:
                                        qty_120 += sl_qty
                            if qty > 0:
                                total_qty += qty
                                unit_price = prod_up_dic.get(product_id, 0.0)
                                loc_prod_dic.update({product_id: (qty, qty_030, qty_3060, qty_6090, qty_90120, qty_120, unit_price)})
                            else:
                                pass
                    elif categ.category_type in ('sfg', 'rm'):
                        in_query = """SELECT distinct(ml.product_id),ml.lot_id,sum(ml.qty_done)
                            FROM stock_move_line ml
                            WHERE 
                                ml.product_id IN %s
                                AND ml.location_dest_id IN %s
                                AND ml.date <= %s
                            GROUP BY
                                ml.product_id, ml.lot_id
                            """
                        self.env.cr.execute(in_query, (tuple(product_ids), tuple([location.id]), self.date))
                        in_res = self.env.cr.dictfetchall()
                        product_loc_dic = {}
                        for stock in in_res:
                            if stock['product_id'] and stock['lot_id']:
                                product_lot_key = '%s_%s'%(str(stock['product_id']), str(stock['lot_id']))
                                product_loc_dic.update({product_lot_key: round(stock['sum'], 2)})
                        out_query = """SELECT distinct(ml.product_id),ml.lot_id,sum(ml.qty_done)
                            FROM stock_move_line ml
                            WHERE 
                                ml.product_id IN %s
                                AND ml.location_id IN %s
                                AND ml.date <= %s
                            GROUP BY
                                ml.product_id, ml.lot_id
                            """
                        self.env.cr.execute(out_query, (tuple(product_ids), tuple([location.id]), self.date))
                        out_res = self.env.cr.dictfetchall()
                        for stock in out_res:
                            if stock['product_id'] and stock['lot_id']:
                                product_lot_key = '%s_%s'%(str(stock['product_id']), str(stock['lot_id']))
                                if product_lot_key in product_loc_dic:
                                    new_qty = round(product_loc_dic[product_lot_key] - round(stock['sum'], 3), 3)
                                    product_loc_dic.update({product_lot_key: new_qty})
                        for product_loc in product_loc_dic:
                            product = prod_obj.browse(int(product_loc.split('_')[0]))
                            lot = lot_obj.browse(int(product_loc.split('_')[1]))
                            lot_qty = round(product_loc_dic[product_loc], 3)
                            total_qty += lot_qty
                            qty, qty_030, qty_3060, qty_6090, qty_90120, qty_120 = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                            unit_price = prod_up_dic.get(product.id, 0.0)
                            if lot_qty > 0:
                                if product.id in loc_prod_dic:
                                    qty = loc_prod_dic[product.id][0]
                                    qty_030 = loc_prod_dic[product.id][1]
                                    qty_3060 = loc_prod_dic[product.id][2]
                                    qty_6090 = loc_prod_dic[product.id][3]
                                    qty_90120 = loc_prod_dic[product.id][4]
                                    qty_120 = loc_prod_dic[product.id][5]
                                qty += lot_qty
                                diff = (self.date - lot.create_date.date()).days
                                if diff <= 30:
                                    qty_030 += lot_qty
                                elif diff <= 60:
                                    qty_3060 += lot_qty
                                elif diff <= 90:
                                    qty_6090 += lot_qty
                                elif diff <= 120:
                                    qty_90120 += lot_qty
                                else:
                                    qty_120 += lot_qty
                                loc_prod_dic.update({product.id: (qty, qty_030, qty_3060, qty_6090, qty_90120, qty_120, unit_price)})
            total_quantity += round(total_qty, 3)
            if total_qty != 0:
                col += 1
                ws.write(col, 0, 'Location:', title_left)
                ws.write(col, 1, location.display_name, title_left)
                col += 1
                ws.row(col).height = 500
                ws.write(col, 0, 'Internal Reference', title_centre)
                ws.write(col, 1, 'Product', title_centre)
                ws.write(col, 2, 'Product Category', title_centre)
                ws.write(col, 3, 'Stock In Hand', title_centre)
                ws.write(col, 4, 'Unit Cost', title_centre)
                ws.write(col, 5, '0-30', title_centre)
                ws.write(col, 6, '0-30 Value', title_centre)
                ws.write(col, 7, '31-60', title_centre)
                ws.write(col, 8, '31-60 Value', title_centre)
                ws.write(col, 9, '61-90', title_centre)
                ws.write(col, 10, '61-90 Value', title_centre)
                ws.write(col, 11, '91-120', title_centre)
                ws.write(col, 12, '91-120 Value', title_centre)
                ws.write(col, 13, '121+', title_centre)
                ws.write(col, 14, '121+ Value', title_centre)
                col += 1
                for product_id in loc_prod_dic:
                    product = prod_obj.browse(product_id)
                    loc_prod_0 = loc_prod_dic[product_id][0]
                    loc_prod_1 = loc_prod_dic[product_id][1]
                    loc_prod_2 = loc_prod_dic[product_id][2]
                    loc_prod_3 = loc_prod_dic[product_id][3]
                    loc_prod_4 = loc_prod_dic[product_id][4]
                    loc_prod_5 = loc_prod_dic[product_id][5]
                    unit_price = loc_prod_dic[product_id][6]
                    value_loc_prod_1 = loc_prod_1 != 0 and round(loc_prod_1*unit_price, 3) or 0.0
                    value_loc_prod_2 = loc_prod_2 != 0 and round(loc_prod_2*unit_price, 3) or 0.0
                    value_loc_prod_3 = loc_prod_3 != 0 and round(loc_prod_3*unit_price, 3) or 0.0
                    value_loc_prod_4 = loc_prod_4 != 0 and round(loc_prod_4*unit_price, 3) or 0.0
                    value_loc_prod_5 = loc_prod_5 != 0 and round(loc_prod_5*unit_price, 3) or 0.0
                    
                    total_value = total_value + value_loc_prod_1 + value_loc_prod_2 + value_loc_prod_3 + value_loc_prod_4 + value_loc_prod_5
                    ws.write(col, 0, product.default_code or '', string_left)
                    ws.write(col, 1, product.name or '', string_left)
                    ws.write(col, 2, product.categ_id.name, string_left)
                    ws.write(col, 3, loc_prod_0 != 0 and round(loc_prod_0, 3) or '', number2d)
                    ws.write(col, 4, unit_price != 0 and round(unit_price, 3) or '', number2d)
                    ws.write(col, 5, loc_prod_1 != 0 and round(loc_prod_1, 3) or '', number2d)
                    ws.write(col, 6, value_loc_prod_1 or '', number2d)
                    ws.write(col, 7, loc_prod_2 != 0 and round(loc_prod_2, 3) or '', string_left)
                    ws.write(col, 8, value_loc_prod_2 or '', number2d)
                    ws.write(col, 9, loc_prod_3 != 0 and round(loc_prod_3, 3) or '', number2d)
                    ws.write(col, 10, value_loc_prod_3 and round(loc_prod_3*unit_price, 3) or '', number2d)
                    ws.write(col, 11, loc_prod_4 != 0 and round(loc_prod_4, 3) or '', number2d)
                    ws.write(col, 12, value_loc_prod_4 or '', number2d)
                    ws.write(col, 13, loc_prod_5 != 0 and round(loc_prod_5, 3) or '', number2d)
                    ws.write(col, 14, value_loc_prod_5 or '', number2d)
                    col += 1
        
        ws.row(col).height = 300
        ws.write_merge(col, col, 0, 2, 'TOTAL QUANTITY', title_centre_300)
        ws.write(col, 3, total_quantity and round(total_quantity, 3) or '', number2d_bold)
        ws.write_merge(col, col, 4, 14, '', title_centre_300)
        col += 1
        ws.row(col).height = 300
        ws.write_merge(col, col, 0, 2, 'TOTAL VALUE', title_centre_300)
        ws.write(col, 3, total_value or '', number2d_bold)
        ws.write_merge(col, col, 4, 14, '', title_centre_300)
        col += 1
        
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Stock Ageing Report.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/stock/ageing?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    