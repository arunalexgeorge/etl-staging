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


class Company(models.Model):
    _inherit = 'res.company'
    
    gst_fiscal_position_id = fields.Many2one('account.fiscal.position', "Fiscal Position(GST)")
    igst_fiscal_position_id = fields.Many2one('account.fiscal.position', "Fiscal Position(IGST)")
    tcs_tax_id = fields.Many2one('account.tax', 'TCS Tax')
    