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
from datetime import timedelta, datetime, date

class Partner(models.Model):
    _inherit = 'res.partner'
    
    credit_period_days = fields.Integer('Credit Period(Days)', copy=False)

class Company(models.Model):
    _inherit = 'res.company'
        
    def _get_user_fiscal_lock_date(self):
        """Get the fiscal lock date for this company depending on the user"""
        # self.ensure_one()
        lock_date = max(self.period_lock_date or date.min, self.fiscalyear_lock_date or date.min)
        if self.user_has_groups('account.group_account_manager'):
            lock_date = self.fiscalyear_lock_date or date.min
        return lock_date
    
    