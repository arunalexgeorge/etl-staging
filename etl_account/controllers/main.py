# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.http import request, content_disposition
import base64

class SalesRegisterReport(http.Controller):

    @http.route('/sales/register', type='http', auth="public")
    def download_document(self, id, filename=None, **kw):
        record_obj = request.env['sale.register']
        res = record_obj.browse(int(id)).read(['report_file', 'report_file_name'])[0]
        filecontent = base64.b64decode(res.get('report_file') or '')
        return request.make_response(filecontent,
                            [('Content-Type', 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(res.get('report_file_name')))])
        

class PurchaseRegisterReport(http.Controller):

    @http.route('/purchase/register', type='http', auth="public")
    def download_document(self, id, filename=None, **kw):
        record_obj = request.env['purchase.register']
        res = record_obj.browse(int(id)).read(['report_file', 'report_file_name'])[0]
        filecontent = base64.b64decode(res.get('report_file') or '')
        return request.make_response(filecontent,
                            [('Content-Type', 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(res.get('report_file_name')))])

class DocSummary(http.Controller):

    @http.route('/doc/summary', type='http', auth="public")
    def download_document(self, id, filename=None, **kw):
        record_obj = request.env['doc.summary']
        res = record_obj.browse(int(id)).read(['report_file', 'report_file_name'])[0]
        filecontent = base64.b64decode(res.get('report_file') or '')
        return request.make_response(filecontent,
                            [('Content-Type', 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(res.get('report_file_name')))])

class HsnSummaryReport(http.Controller):

    @http.route('/hsn/summary', type='http', auth="public")
    def download_document(self, id, filename=None, **kw):
        record_obj = request.env['hsn.report']
        res = record_obj.browse(int(id)).read(['report_file', 'report_file_name'])[0]
        filecontent = base64.b64decode(res.get('report_file') or '')
        return request.make_response(filecontent,
                            [('Content-Type', 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(res.get('report_file_name')))])
        

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: