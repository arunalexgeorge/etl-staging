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

from . import models
from . import reports
from . import wizard
from . import controllers
from .hooks import post_init_hook
from odoo import api, fields, SUPERUSER_ID, _


def _uninstall_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    xml_ids = [
        'sale.sale_order_personal_rule',
        'sale.sale_order_see_all'
    ]
    for xml_id in xml_ids:
        act_window = env.ref(xml_id, raise_if_not_found=False)
        if xml_id == 'sale.sale_order_personal_rule':
            act_window.domain_force = "['|',('user_id','=',user.id),('user_id','=',False)]"
        if xml_id == 'sale.sale_order_see_all':
            act_window.domain_force = [(1, '=', 1)]
