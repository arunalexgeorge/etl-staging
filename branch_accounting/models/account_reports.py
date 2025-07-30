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

from odoo import models, fields, api, _

class AccountReport(models.AbstractModel):
    _inherit = 'account.report'

    filter_branch = None

    filter_branch = fields.Boolean(string="Branches",
        compute=lambda x: x._compute_report_option_filter('filter_branch'), readonly=False, store=True, depends=['root_report_id'],)

    def _init_options_branch(self, options, previous_options=None):
        
        options['branch'] = False
        # options['branch_ids'] = previous_options and previous_options.get('branch_ids') or []
        # selected_branch_ids = [int(branch) for branch in options['branch_ids']]
        # selected_branchs = selected_branch_ids and self.env['res.branch'].browse(selected_branch_ids) or self.env['res.branch']
        # options['selected_branch_ids'] = selected_branchs.mapped('name')
        

    @api.model
    def _get_options_branch_domain(self, options):
        branch_ids = options.get('branch_ids', [])
        if not branch_ids:
            if 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = self.env.user.branch_ids.ids
        return [('branch_id', 'in', branch_ids)]

    def _get_options_domain(self, options, date_scope):
        domain = super(AccountReport, self)._get_options_domain(options, date_scope)
        domain += self._get_options_branch_domain(options)
        return domain
