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
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang, xlwt
from io import BytesIO
import base64
import html2text
from datetime import datetime, timedelta
import json
                
class ProductionPlanning(models.TransientModel):
    _name = 'production.planning.report'
    _description = 'Production Planning Report'

    order_ids = fields.Many2many('sale.order', string='Sales Orders')
    report_file = fields.Binary('Report File')
    report_file_name = fields.Char('Report File Name')
    
    def print_report(self):
        wb = xlwt.Workbook()
        title_centre = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_blank = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        string_left = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz left;')
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin, top thin; align: horiz right;',num_format_str='#,##0.000;-#,##0.000')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        company = self.env.user.company_id
        ws = wb.add_sheet('Production Planning Report')
        sale_obj = self.env['sale.order']
        ws.write(0, 0, 'Product', title_centre)
        ws.write(0, 1, 'Grade', title_centre)
        ws.write(0, 2, 'Compound', title_centre)
        ws.write(0, 3, 'No. of Bags', title_centre)
        ws.write(0, 4, 'No. of Belts', title_centre)
        ws.write(0, 5, 'Customer', title_centre)
        ws.col(0).width = 10000
        ws.col(2).width = 4000
        ws.col(5).width = 6000
        row = 1
        for order in self.order_ids:
            for line in order.order_line:
                product = line.product_id
                ws.write(row, 0, product.name, string_left)
                ws.write(row, 1, product.product_group2_id and product.product_group2_id.name or '', string_left)
                ws.write(row, 2, product.product_compound_id and product.product_compound_id.name or '', string_left)
                ws.write(row, 5, order.partner_id.name or '', string_left)
                row += 1
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodestring(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Production Planning Report.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/production_planning/report?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    