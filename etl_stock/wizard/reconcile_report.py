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
         
class ReconcileReport(models.TransientModel):
    _name = 'reconcile.report'
    _description = 'Reconcile Report' 

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    categ_ids = fields.Many2many('product.category', string='Categories')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Reconciliation Report')
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
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_bold_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on;border: bottom thin, top thin, left thin, right thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number0d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;; align: horiz right;',num_format_str='###0;###0')
        number0d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='###0;###0')
        for i in range(0, 13):
            ws.col(i).width = 4000
        ws.col(2).width = 8000
        ws.write_merge(0, 1, 0, 6, 'Reconciliation Report', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(2, 3, 0, 6, date, title_centre_300)
        col = 5
        ws.row(5).height = 500
        ws.write(5, 0, 'Txn. Date', title_centre)
        ws.write(5, 1, 'Item No.', title_centre)
        ws.write(5, 2, 'Item Description', title_centre)
        ws.write(5, 3, 'UOM', title_centre)
        ws.write(5, 4, 'Opening Balance', title_centre)
        ws.write(5, 5, 'Receipt', title_centre)
        ws.write(5, 6, 'Material Issue', title_centre)
        ws.write(5, 7, 'Closing Balance', title_centre)
        ws.write(5, 8, 'Product Category', title_centre)
        ws.write(5, 9, 'Unit Price', title_centre)
        ws.write(5, 10, 'Receipt Amount', title_centre)
        ws.write(5, 11, 'Issue Amount', title_centre)
        ws.write(5, 12, 'Closing Amount', title_centre)
        col += 1
        categ_ids = [categ.id for categ in self.categ_ids]
        svl_obj = self.env['stock.valuation.layer']
        for categ_id in categ_ids:
            products = self.env['product.product'].search([
                ('categ_id', '=', categ_id), 
                ('type', '!=', 'detailed_service')
                ])
            for product in products:
                ob, in_qty, out_qty, cb = 0, 0, 0, 0
                unit_price, in_amount, out_amount, balance_amount = 0, 0, 0, 0
                
                ob_svls = svl_obj.search([
                    ('product_id', '=', product.id), 
                    ('create_date', '<', self.start_date)
                    ])
                for ob_svl in ob_svls:
                    ob += ob_svl.quantity
                    balance_amount += ob_svl.value
                tr_svls = svl_obj.search([
                    ('product_id', '=', product.id), 
                    ('create_date', '>=', self.start_date),
                    ('create_date', '<=', self.end_date),
                    ])
                for tr_svl in tr_svls:
                    if tr_svl.quantity > 0:
                        in_qty += tr_svl.quantity
                        in_amount += tr_svl.value
                    elif tr_svl.quantity < 0:
                        out_qty += tr_svl.quantity
                        out_amount += tr_svl.value
                    balance_amount += tr_svl.value
                out_qty = abs(out_qty)
                out_amount = abs(out_amount)
                cb = ob + in_qty - out_qty
                if cb != 0:
                    unit_price = balance_amount / cb
                if ob == 0 and in_qty == 0 and out_qty == 0 and cb == 0 and balance_amount == 0:
                    pass
                else:
                    ws.write(col, 0, '', string_left)
                    ws.write(col, 1, product.default_code or '', string_left)
                    ws.write(col, 2, product.name, string_left)
                    ws.write(col, 3, product.uom_id.name, string_left)
                    ws.write(col, 4, ob != 0 and round(ob, 2) or '', number2d)
                    ws.write(col, 5, in_qty != 0 and round(in_qty, 2) or '', number2d)
                    ws.write(col, 6, out_qty != 0 and round(out_qty, 2) or '', number2d)
                    ws.write(col, 7, cb != 0 and round(cb, 2) or '', number2d)
                    ws.write(col, 8, product.categ_id.name, string_left)
                    ws.write(col, 9, unit_price != 0 and round(unit_price, 2) or '', number2d)
                    ws.write(col, 10, in_amount != 0 and round(in_amount, 2) or '', number2d)
                    ws.write(col, 11, out_amount != 0 and round(out_amount, 2) or '', number2d)
                    ws.write(col, 12, balance_amount != 0 and round(balance_amount, 2) or '', number2d)
                    col += 1
        
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Reconciliation Report.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/reconciliation/report?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    