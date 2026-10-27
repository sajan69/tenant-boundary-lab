from django.core.management.base import BaseCommand
from tickets.boundary import verify_request_connection

class Command(BaseCommand):
    help='Verify the request connection uses the expected restricted role and RLS tables.'
    def handle(self,*args,**options):
        verify_request_connection()
        self.stdout.write('Request role and forced RLS table checks passed.')
