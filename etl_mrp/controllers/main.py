# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.main import content_disposition
import base64

class ProductionPlanning(http.Controller):

    @http.route('/production_planning/report', type='http', auth="public")
    def download_document(self, id, filename=None, **kw):
        record_obj = request.env['production.planning.report']
        res = record_obj.browse(int(id)).read(['report_file', 'report_file_name'])[0]
        filecontent = base64.b64decode(res.get('report_file') or '')
        return request.make_response(filecontent,
                            [('Content-Type', 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(res.get('report_file_name')))])


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: