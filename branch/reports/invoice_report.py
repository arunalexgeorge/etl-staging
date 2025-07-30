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


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    branch_id = fields.Many2one('res.branch')
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'allowed_branch_ids' in self._context:
            branches_ids = self._context['allowed_branch_ids']
        else:
            branches_ids = self.env.user.branch_ids.ids
        args += [('branch_id', 'in', branches_ids)]
        return super(AccountInvoiceReport, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'allowed_branch_ids' in self._context:
            branches_ids = self._context['allowed_branch_ids']
        else:
            branches_ids = self.env.user.branch_ids.ids
        domain += [('branch_id', 'in', branches_ids)]
        return super(AccountInvoiceReport, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

    def _select(self):
        return super(AccountInvoiceReport, self)._select() + ", move.branch_id"