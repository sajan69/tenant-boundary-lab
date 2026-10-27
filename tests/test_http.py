import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','boundary.settings')
import django
django.setup()
import unittest
from django.test import RequestFactory
from tickets.http import ApiError,body,text
from tickets.auth_api import LoginLimiter
from tickets.api import page

class HttpBoundaryTests(unittest.TestCase):
    def parse(self,raw,content_type='application/json'):
        return body(RequestFactory().post('/',data=raw,content_type=content_type),('title',),('title',))

    def test_rejects_duplicate_keys_nonfinite_and_invalid_json(self):
        for raw in ('{"title":"one","title":"two"}','{"title":NaN}','{"title":Infinity}','{"title":1e999}','{"title":', '[]','null','{"other":"x"}'):
            with self.subTest(raw=raw),self.assertRaises(ApiError):self.parse(raw)

    def test_requires_utf8_json_and_bounded_actual_body(self):
        for raw,content_type in [(b'\xff','application/json'),('\ufeff{"title":"x"}','application/json'),('{"title":"x"}','text/plain'),('{"title":"x"}','application/json; charset=latin1')]:
            with self.assertRaises(ApiError):self.parse(raw,content_type)
        with self.assertRaises(ApiError) as caught:self.parse('{"title":"'+'x'*65536+'"}')
        self.assertEqual(caught.exception.status,413)

    def test_text_limits_and_controls_are_enforced(self):
        for value in ('',True,12,[],{},'x'*201,'bad\x00value','bad\ud800value'):
            with self.assertRaises(ApiError):text(value,200)
        self.assertEqual(text('  Title  ',200),'Title')
        self.assertEqual(text('line one\nline two',2000,multiline=True),'line one\nline two')

    def test_rate_limit_expires_and_has_bounded_peer_capacity(self):
        now=[0];limiter=LoginLimiter(attempts=2,capacity=1,clock=lambda:now[0])
        self.assertTrue(limiter.allow('a'));self.assertTrue(limiter.allow('a'));self.assertFalse(limiter.allow('a'))
        self.assertFalse(limiter.allow('b'));self.assertEqual(len(limiter.entries),1)
        now[0]=60;self.assertTrue(limiter.allow('b'));self.assertEqual(len(limiter.entries),1)

    def test_page_cap_is_explicit_instead_of_advertising_unavailable_next_page(self):
        result=page([1,2],1,10000,lambda value:value)
        self.assertTrue(result['has_more']);self.assertTrue(result['pagination_limit_reached']);self.assertIsNone(result['next_offset'])
