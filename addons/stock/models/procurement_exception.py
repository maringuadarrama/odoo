# Part of Odoo. See LICENSE file for full copyright and licensing details.


class ProcurementException(Exception):
    '''
    An exception raised by ProcurementGroup `run` containing all the faulty
    procurements.
    '''
    def __init__(self, procurement_exceptions):
        ''':param procurement_exceptions: a list of tuples containing the faulty
        procurement and their error messages
        :type procurement_exceptions: list
        '''
        self.procurement_exceptions = procurement_exceptions
