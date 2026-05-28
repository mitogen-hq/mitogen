# -*- coding: utf-8 -*-
import sys
import unittest

import testlib

import nonascii_pkg.with_bom.utf8
import nonascii_pkg.with_coding.cp1252
import nonascii_pkg.with_coding.iso8859_15
import nonascii_pkg.with_coding.latin1
import nonascii_pkg.with_coding.utf8


class UndeclaredTest(testlib.RouterMixin, testlib.TestCase):
    @unittest.skipIf(sys.version_info < (3, 0), 'Python 2.x, default source encoding is ascii')
    def test_utf8(self):
        import nonascii_pkg.undeclared.utf8
        conn = self.router.local(python_path='python3')
        self.assertEqual(
            u'Hello world, Καλημέρα κόσμε, コンニチハ',
            conn.call(nonascii_pkg.with_bom.utf8.string_literal),
        )


class WithBomTest(testlib.RouterMixin, testlib.TestCase):
    def test_utf8(self):
        conn = self.router.local()
        self.assertEqual(
            u'Hello world, Καλημέρα κόσμε, コンニチハ',
            conn.call(nonascii_pkg.with_bom.utf8.string_literal),
        )


class WithCodingTest(testlib.RouterMixin, testlib.TestCase):
    def test_cp1252(self):
        conn = self.router.local()
        self.assertEqual(
            u'Hello euro sign, Olá €, Hello trademark, Hello ™',
            conn.call(nonascii_pkg.with_coding.cp1252.string_literal),
        )

    def test_iso8859_15(self):
        conn = self.router.local()
        self.assertEqual(
            u'Hello euro sign, Hello €',
            conn.call(nonascii_pkg.with_coding.iso8859_15.string_literal),
        )

    def test_latin1(self):
        conn = self.router.local()
        self.assertEqual(
            u'Hello world, Olá mundo, Hej världen',
            conn.call(nonascii_pkg.with_coding.latin1.string_literal),
        )

    def test_utf8(self):
        conn = self.router.local()
        self.assertEqual(
            u'Hello world, Καλημέρα κόσμε, コンニチハ',
            conn.call(nonascii_pkg.with_coding.utf8.string_literal),
        )
