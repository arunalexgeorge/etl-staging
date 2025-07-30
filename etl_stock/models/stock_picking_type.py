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

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime


class PickingType(models.Model):
    _inherit = "stock.picking.type"
    
    @api.depends('company_id')
    def _compute_warehouse_id(self):
        if self.warehouse_id:
            return
        if self.company_id:
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.company_id.id),
                ('branch_id', '=', self.env.user.branch_id.id)
                ], limit=1)
            self.warehouse_id = warehouse
        else:
            self.warehouse_id = False
    
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', compute='_compute_warehouse_id', 
        store=True, readonly=False, ondelete='cascade',check_company=True)
    quality_check = fields.Boolean('Quality Check')