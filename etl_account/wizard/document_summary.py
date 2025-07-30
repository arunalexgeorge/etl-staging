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
         
class DocSummary(models.TransientModel):
    _name = 'doc.summary'
    _description = 'Document Summary' 

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Document Summary')
        title_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_left_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz left, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_blank = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_300 = xlwt.easyxf('font: height 300, name Arial, colour_index black, bold on; align: horiz centre, vert centre;border: bottom thin, top thin, left thin, right thin')
        title_left = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz left;')
        string_left = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz left;')
        string_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;')
        number_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;',num_format_str='#,##0;-#,##0')
        string_left_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz left;')
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_bold_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number0d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0;-#,##0')
        ws.col(0).width = 12000
        for i in range(1, 6):
            ws.col(i).width = 6000
        ws.write_merge(0, 0, 0, 5, 'GSTR1 - Document Summary', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(1, 1, 0, 5, date, title_centre_300)
        ws.write(4, 0, 'Nature of Document', title_centre)
        ws.write_merge(4, 4, 1, 2, 'Serial No.', title_centre)
        ws.write(4, 3, 'Total No.', title_centre)
        ws.write(4, 4, 'Cancelled', title_centre)
        ws.write(4, 5, 'Nett. Issued', title_centre)
        ws.write(5, 1, 'From', title_centre)
        ws.write(5, 2, 'To', title_centre)
        ws.write(6, 0, 'Invoices for outward supply (Sales)', title_left)
        ws.write(7, 0, ' '*10+'Outward Supply', string_left)
        ws.write(8, 0, ' '*10+'Outward Supply Retreading', string_left)
        ws.write(9, 0, ' '*10+'Outward Supply - Export', string_left)
        ws.write(10, 0, ' '*10+'Outward Supply - Stock Transfer', string_left)
        ws.write(11, 0, 'Debit Note', title_left)
        ws.write(12, 0, 'Credit Note', title_left)
        branch_id = self.env.user.branch_id.id
        move_obj = self.env['account.move']
        inv_domain = [
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', 'in', ('posted', 'cancel')),
            ('branch_id', '=', branch_id),
            ('so_type', 'not in', ('export', 'rt_sales', 'stock'))
            ]
        out_invoices = move_obj.search(inv_domain, order='date,name')
        if out_invoices:
            out_invoice_list = [out_invoice.name for out_invoice in out_invoices]
            out_invoice_count = len(out_invoice_list)
            can_invoice_list = [out_invoice.name for out_invoice in out_invoices if out_invoice.state == 'cancel']
            can_invoice_count = len(can_invoice_list)
            net_count = out_invoice_count - can_invoice_count
            ws.write(7, 1, out_invoice_list[0], string_left)
            ws.write(7, 2, out_invoice_list[-1], string_left)
            ws.write(7, 3, out_invoice_count or '', number0d)
            ws.write(7, 4, can_invoice_count or '', number0d)
            ws.write(7, 5, net_count or '', number0d)
        rt_domain = [
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', 'in', ('posted', 'cancel')),
            ('branch_id', '=', branch_id),
            ('so_type', '=', 'rt_sales')
            ]
        rt_invoices = move_obj.search(rt_domain, order='date,name')
        if rt_invoices:
            out_invoice_list = [out_invoice.name for out_invoice in rt_invoices]
            out_invoice_count = len(out_invoice_list)
            can_invoice_list = [out_invoice.name for out_invoice in rt_invoices if out_invoice.state == 'cancel']
            can_invoice_count = len(can_invoice_list)
            net_count = out_invoice_count - can_invoice_count
            ws.write(8, 1, out_invoice_list[0], string_left)
            ws.write(8, 2, out_invoice_list[-1], string_left)
            ws.write(8, 3, out_invoice_count or '', number0d)
            ws.write(8, 4, can_invoice_count or '', number0d)
            ws.write(8, 5, net_count or '', number0d)
        exp_domain = [
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', 'in', ('posted', 'cancel')),
            ('branch_id', '=', branch_id),
            ('so_type', '=', 'export')
            ]
        
        exp_invoices = move_obj.search(exp_domain, order='date,name')
        if exp_invoices:
            out_invoice_list = [out_invoice.name for out_invoice in exp_invoices]
            out_invoice_count = len(out_invoice_list)
            can_invoice_list = [out_invoice.name for out_invoice in exp_invoices if out_invoice.state == 'cancel']
            can_invoice_count = len(can_invoice_list)
            net_count = out_invoice_count - can_invoice_count
            ws.write(9, 1, out_invoice_list[0], string_left)
            ws.write(9, 2, out_invoice_list[-1], string_left)
            ws.write(9, 3, out_invoice_count or '', number0d)
            ws.write(9, 4, can_invoice_count or '', number0d)
            ws.write(9, 5, net_count or '', number0d)
        st_domain = [
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', 'in', ('posted', 'cancel')),
            ('branch_id', '=', branch_id),
            ('so_type', '=', 'stock')
            ]
        
        st_invoices = move_obj.search(st_domain, order='date,name')
        if st_invoices:
            out_invoice_list = [out_invoice.name for out_invoice in st_invoices]
            out_invoice_count = len(out_invoice_list)
            can_invoice_list = [out_invoice.name for out_invoice in st_invoices if out_invoice.state == 'cancel']
            can_invoice_count = len(can_invoice_list)
            net_count = out_invoice_count - can_invoice_count
            ws.write(10, 1, out_invoice_list[0], string_left)
            ws.write(10, 2, out_invoice_list[-1], string_left)
            ws.write(10, 3, out_invoice_count or '', number0d)
            ws.write(10, 4, can_invoice_count or '', number0d)
            ws.write(10, 5, net_count or '', number0d)
        dn_domain = [
            ('move_type', '=', 'in_refund'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('state', 'in', ('posted', 'cancel')),
            ('branch_id', '=', branch_id),
            ]
        
        dn_invoices = move_obj.search(dn_domain, order='date,name')
        if dn_invoices:
            out_invoice_list = [out_invoice.name for out_invoice in dn_invoices]
            out_invoice_count = len(out_invoice_list)
            can_invoice_list = [out_invoice.name for out_invoice in dn_invoices if out_invoice.state == 'cancel']
            can_invoice_count = len(can_invoice_list)
            ws.write(11, 1, out_invoice_list[0], string_left)
            ws.write(11, 2, out_invoice_list[-1], string_left)
            ws.write(11, 3, out_invoice_count-can_invoice_count or '', number0d)
            ws.write(11, 4, can_invoice_count or '', number0d)
            ws.write(11, 5, out_invoice_count or '', number0d)
        cn_domain = [
            ('move_type', '=', 'out_refund'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', 'in', ('posted', 'cancel')),
            ('branch_id', '=', branch_id),
            ]
        
        cn_invoices = move_obj.search(cn_domain, order='date,name')
        if cn_invoices:
            out_invoice_list = [out_invoice.name for out_invoice in cn_invoices]
            out_invoice_count = len(out_invoice_list)
            can_invoice_list = [out_invoice.name for out_invoice in cn_invoices if out_invoice.state == 'cancel']
            can_invoice_count = len(can_invoice_list)
            net_count = out_invoice_count - can_invoice_count
            ws.write(12, 1, out_invoice_list[0], string_left)
            ws.write(12, 2, out_invoice_list[-1], string_left)
            ws.write(12, 3, out_invoice_count or '', number0d)
            ws.write(12, 4, can_invoice_count or '', number0d)
            ws.write(12, 5, net_count or '', number0d)
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Document Summary.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/doc/summary?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    