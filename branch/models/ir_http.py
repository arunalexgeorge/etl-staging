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

from odoo import api, models
from odoo.http import request

class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """ Add information about iap enrich to perform """
        user = request.env.user
        session_info = super(Http, self).session_info()
        branches = {}
        for branch in user.branch_ids:
            branches.update({
                branch.id: {
                    'id': branch.id,
                    'name': branch.name,
                    'company': branch.company_id.id,
                    }
                })
        if self.env.user.has_group('base.group_user'):
            session_info.update({
                "user_companies": {
                    'current_company': user.company_id.id , 
                    'allowed_companies': {
                        comp.id: {
                            'id': comp.id,
                            'name': comp.name,
                        } for comp in user.company_ids
                    },
                },
                "user_branches": {
                    'current_branch': user.branch_id.id, 
                    'allowed_branches': branches,
                    },
                "currencies": self.get_currencies(),
                "show_effect": True,
                "display_switch_company_menu": user.has_group('base.group_multi_company') and len(user.company_ids) > 1,
                "display_switch_branch_menu": len(user.branch_ids) > 1,
                "allowed_branch_ids" : user.branch_ids.ids,
                "support_url": "https://www.steigendit.com/web"
            })
        return session_info
