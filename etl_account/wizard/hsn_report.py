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

from odoo import _, api, fields, models, Command, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang, xlwt
from io import BytesIO
import base64
         
class HsnReport(models.TransientModel):
    _name = 'hsn.report'
    _description = 'HSN Report' 

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('GSTR1-HSN/SAC Summary')
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
        ws.write_merge(0, 0, 0, 6, 'GSTR1-HSN/SAC Summary', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(1, 1, 0, 6, date, title_centre_300)
        ws.write_merge(2, 2, 0, 3, 'Total Vouchers', title_left)
        ws.write_merge(3, 3, 0, 3, ' '*20+'Included in HSN/SAC Summary', string_left)
        ws.write_merge(4, 4, 0, 3, ' '*20+'Incomplete Information in HSN/SAC Summary (Corrections needed)', string_left)
        ws.write(5, 0, 'HSN/SAC', title_centre)
        ws.write(5, 1, 'Description', title_centre)
        ws.write(5, 2, 'Type of Supply', title_centre)
        ws.write(5, 3, 'UQC', title_centre)
        ws.write(5, 4, 'Total Quantity', title_centre)
        ws.write(5, 5, 'Total Value', title_centre)
        ws.write(5, 6, 'Tax Rate', title_centre)
        ws.write(5, 7, 'Taxable Amount', title_centre)
        ws.write(5, 8, 'Integrated Tax Amount', title_centre)
        ws.write(5, 9, 'Central Tax Amount', title_centre)
        ws.write(5, 10, 'State Tax Amount', title_centre)
        ws.write(5, 11, 'TCS Amount', title_centre)
        ws.write(5, 12, 'Total Tax Amount', title_centre)
        col = 6
        branch_id = self.env.user.branch_id.id
        invoices = self.env['account.move'].search([
            ('move_type', 'in', ('out_invoice', 'out_refund', 'in_refund')),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', '=', 'posted'),
            ('branch_id', '=', branch_id)
            ], order='invoice_date,name')
        total_count = len(invoices.ids)
        ws.write(2, 4, total_count, number0d_bold)
        missing_products = []
        missing_count = 0
        hsc_tax_dic = {}
        for invoice in invoices:
            if invoice.so_type == 'stock' and invoice.partner_id.state_id.id == invoice.branch_id.partner_id.state_id.id:
                continue
            missing = False
            sign = 1
            if invoice.move_type == 'out_refund':
                sign = -1
            for line in invoice.invoice_line_ids:
                tax_gst, tax_igst, tax_tcs = 0, 0, 0
                if line.product_id and line.product_id.hs_code_id:
                    hsn = line.product_id.hs_code_id.name
                    taxable_value = line.price_subtotal*sign
                    total_value = line.price_total*sign
                    total_qty = line.quantity*sign
                    if line.tax_ids:
                        tax_perc = False
                        for tax in line.tax_ids:
                            group = tax.tax_group_id.name
                            tax_value = tools.float_round(taxable_value * tax.amount * 0.01, precision_rounding=0.01)
                            if group == 'GST':
                                tax_perc = str(tax.amount)
                                tax_gst = tax_value
                            elif group == 'IGST':
                                tax_perc = str(tax.amount)
                                tax_igst = tax_value
                            elif group == 'TCS':
                                tcs_base = taxable_value + tax_gst + tax_igst
                                tax_tcs = tools.float_round(tcs_base * tax.amount * 0.01, precision_rounding=0.01)
                                
                    else:
                        tax_perc = '0.0'
                    if tax_perc:
                            hsn_perc = '%s:%s'%(hsn, tax_perc)
                            if hsn_perc in hsc_tax_dic:
                                hsc_tax_dic.update({
                                    hsn_perc: {
                                        'total_qty': hsc_tax_dic[hsn_perc]['total_qty'] + total_qty,
                                        'total_value': hsc_tax_dic[hsn_perc]['total_value'] + total_value,
                                        'taxable_value': hsc_tax_dic[hsn_perc]['taxable_value'] + taxable_value,
                                        'tax_gst': hsc_tax_dic[hsn_perc]['tax_gst'] + tax_gst,
                                        'tax_igst': hsc_tax_dic[hsn_perc]['tax_igst'] + tax_igst,
                                        'tax_tcs': hsc_tax_dic[hsn_perc]['tax_tcs'] + tax_tcs
                                        }
                                    })
                            else:
                                hsc_tax_dic.update({
                                    hsn_perc: {
                                        'total_qty': total_qty,
                                        'total_value': total_value,
                                        'taxable_value': taxable_value,
                                        'tax_gst': tax_gst,
                                        'tax_igst': tax_igst,
                                        'tax_tcs': tax_tcs
                                        }
                                    })
                else:
                    missing = True
                    missing_products.append('%s:%s'%(line.name, line.move_id.name))
            if missing:
                missing_count += 1
        total_value, taxable_value, igst, cgst, sgst, total = 0, 0, 0, 0, 0, 0
        tcs = 0
        ws.write(3, 4, total_count-missing_count, number0d)
        ws.write(4, 4, missing_count, number0d)
        hsn_list_dic = {}
        hsc_tax_list = []
        for hsn in hsc_tax_dic:
            hsc_tax_list.append({
                'hsn': hsn,
                'value': hsc_tax_dic[hsn]
                })
        for hsn in self.env['hs.code'].search([]):
            hsn_list_dic.update({hsn.name: hsn})
        hsc_tax_list = sorted(hsc_tax_list, key=lambda k: k['hsn'])
        for hsn_tax in hsc_tax_list:
            hsn = hsn_tax['hsn']
            hsn_split = hsn.split(':')
            hsn_code = hsn_split[0]
            perc = float(hsn_split[1])
            hsn_igst = hsc_tax_dic[hsn]['tax_igst']
            igst += hsn_igst
            gst = hsc_tax_dic[hsn]['tax_gst']/2
            gst = tools.float_round(gst, precision_rounding=0.01)
            tax_cgst = gst
            cgst += tax_cgst
            tax_sgst = gst
            sgst += tax_sgst
            tax_tcs = hsc_tax_dic[hsn]['tax_tcs']
            tcs += tax_tcs
            c_total_qty = hsc_tax_dic[hsn]['total_qty']
            c_total_value = hsc_tax_dic[hsn]['total_value']
            c_taxable_value = hsc_tax_dic[hsn]['taxable_value']
            total_value += hsc_tax_dic[hsn]['total_value']
            taxable_value += hsc_tax_dic[hsn]['taxable_value']
            total_tax = hsn_igst + tax_cgst + tax_sgst + tax_tcs
            total += total_tax
            ws.write(col, 0, hsn_code, string_left)
            ws.write(col, 1, hsn_list_dic[hsn_code].desc or '', string_left)
            ws.write(col, 2, hsn_list_dic[hsn_code].type or '', string_left)
            ws.write(col, 3, hsn_list_dic[hsn_code].uqc or '', string_left)
            ws.write(col, 4, c_total_qty, number2d)
            ws.write(col, 5, c_total_value, number2d)
            ws.write(col, 6, round(perc, 2), number2d)
            ws.write(col, 7, c_taxable_value, number2d)
            ws.write(col, 8, hsn_igst != 0 and round(hsn_igst, 2) or '', number2d)
            ws.write(col, 9, tax_cgst != 0 and round(tax_cgst, 2) or '', number2d)
            ws.write(col, 10, tax_sgst != 0 and round(tax_sgst, 2) or '', number2d)
            ws.write(col, 11, tax_tcs != 0 and round(tax_tcs, 2) or '', number2d)
            ws.write(col, 12, round(total_tax, 2), number2d)
            col += 1
        
        ws.write_merge(col, col, 0, 4, 'Grand Total', title_centre)
        ws.write(col, 5, round(total_value, 2), number2d_bold_bg)
        ws.write(col, 6, '', number2d_bold_bg)
        ws.write(col, 7, round(taxable_value, 2), number2d_bold_bg)
        ws.write(col, 8, igst != 0 and round(igst, 2) or '', number2d_bold_bg)
        ws.write(col, 9, cgst != 0  and round(cgst, 2) or '', number2d_bold_bg)
        ws.write(col, 10, sgst != 0  and round(sgst, 2) or '', number2d_bold_bg)
        ws.write(col, 11, tcs != 0  and round(tcs, 2) or '', number2d_bold_bg)
        ws.write(col, 12, total != 0  and round(total, 2) or '', number2d_bold_bg)
        col += 3
        if missing_products:
            ws.write_merge(col, col, 0, 3, 'HSN Missing Products:', title_left)
            col += 1
            ws.write_merge(col, col, 0, 2, 'Product', title_left)
            ws.write(col, 3, 'Invoice Number', title_left)
        col += 1
        for missing_product in missing_products:
            ws.write_merge(col, col, 0, 2, missing_product.split(':')[0], string_left)
            ws.write(col, 3, missing_product.split(':')[1], string_left)
            col += 1
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'HSN Summary.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/hsn/summary?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    