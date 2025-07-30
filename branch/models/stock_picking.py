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
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        user = self.env.user
        if 'no_branch_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            args += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(StockPicking, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)

    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        user = self.env.user
        if 'no_branch_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            domain += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(StockPicking, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    @api.model
    def default_get(self, default_fields):
        res = super(StockPicking, self).default_get(default_fields)
        if self.env.user.branch_id:
            res.update({
                'branch_id' : self.env.user.branch_id.id or False
            })
        return res

    branch_id = fields.Many2one('res.branch', string="Branch")

