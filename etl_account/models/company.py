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
    
    irn_access_token = fields.Char('Access Token')
    irn_url = fields.Char('IRN url')
    irn_eway_url = fields.Char('IRN-Eway url')
    eway_url = fields.Char('Eway url')
    legal_name = fields.Char('Legal Name')
    trade_name = fields.Char('Trade Name')
    company_footer = fields.Html('Invoice Footer')
    last_reconciled_journal_id = fields.Many2one('account.journal', 'Account')
    last_reconciled_date = fields.Date('BSR Date')
    
    