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
import pytz

class SerialReport(models.TransientModel):
    _name = 'serial.report'
    _description = 'Serial Report' 

    date = fields.Datetime('As on')
    categ_ids = fields.Many2many('product.category', string='Categories')
    location_ids = fields.Many2many('stock.location', string='Locations')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    branch_ids = fields.Many2many('res.branch', string='Branches', required=True)
    
    @api.model
    def default_get(self, default_fields):
        res = super(SerialReport, self).default_get(default_fields)
        res.update({'branch_ids' : self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)})
        return res
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Serial Numbers Report')
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
        ws.col(1).width = 8000
        ws.write_merge(0, 0, 0, 5, 'Serial Numbers Report', title_centre_300)
        date_str = self.date.strftime('%d-%m-%Y %H:%M:%S')
        date_india = pytz.utc.localize(datetime.strptime(date_str, '%d-%m-%Y %H:%M:%S')).astimezone(pytz.timezone(('Asia/Calcutta')))
        date_str_india = date_india.strftime("%d-%m-%Y %H:%M:%S")
        
        date_india = datetime.strptime(date_str_india, '%d-%m-%Y %H:%M:%S')
        date = 'As on: ' + date_str_india
        ws.write_merge(1, 1, 0, 5, date, title_left)
        prod_obj = self.env['product.product']
        if self.location_ids:
            locations = self.location_ids
        else:
            locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        col = 2
        ss_obj = self.env['stock.serial']
        ws.write(col, 0, 'Internal Reference', title_centre)
        ws.write(col, 1, 'Product Name', title_centre)
        ws.write(col, 2, 'Product Category', title_centre)
        ws.write(col, 3, 'Lot Number', title_centre)
        ws.write(col, 4, 'Serial Number', title_centre)
        ws.write(col, 5, 'Quantity', title_centre)
        for location in locations:
            loc_qty = False
            for categ in self.categ_ids:
                domain = [
                    ('categ_id', '=', categ.id), 
                    ('type', '!=', 'detailed_service')
                    ]
                product_ids = prod_obj.search(domain, order='name').ids
                if product_ids:
                    in_dic = self.env['stock.serial.location'].get_qty_date(product_ids, location.id, self.date)
                    serial_ids = [serial_id for serial_id in in_dic]
                    sn_ids = ss_obj.with_context(no_filter=True).search([('id', 'in', serial_ids)], order='product_id,name').ids
                    for serial_id in sn_ids:
                        serial = ss_obj.with_context(no_filter=True).browse(serial_id)
                        product = serial.product_id
                        qty = in_dic[serial_id]
                        if round(qty, 3) != 0:
                            if not loc_qty:
                                col += 1
                                ws.write(col, 0, 'Location:', title_left)
                                ws.write(col, 1, location.display_name, title_left)
                                loc_qty = True
                                col += 1
                            ws.write(col, 0, product.default_code or '', string_left)
                            ws.write(col, 1, product.name or '', string_left)
                            ws.write(col, 2, product.categ_id.name, string_left)
                            ws.write(col, 3, serial.lot_id.name, string_left)
                            ws.write(col, 4, serial.name, string_left)
                            ws.write(col, 5, qty, number2d)
                            col += 1
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Serial Numbers Report.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/serial/report?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    