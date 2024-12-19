import sys
import struct
import unittest

try:
    from unittest import mock
except ImportError:
    import mock

import mitogen.core
import mitogen.master
import testlib

from mitogen.core import b


class ConstructorTest(testlib.TestCase):
    klass = mitogen.core.Message

    def test_dst_id_default(self):
        self.assertEqual(self.klass().dst_id, None)

    def test_dst_id_explicit(self):
        self.assertEqual(self.klass(dst_id=1111).dst_id, 1111)

    @mock.patch('mitogen.context_id', 1234)
    def test_src_id_default(self):
        self.assertEqual(self.klass().src_id, 1234)

    def test_src_id_explicit(self):
        self.assertEqual(self.klass(src_id=4321).src_id, 4321)

    @mock.patch('mitogen.context_id', 5555)
    def test_auth_id_default(self):
        self.assertEqual(self.klass().auth_id, 5555)

    def test_auth_id_explicit(self):
        self.assertEqual(self.klass(auth_id=2222).auth_id, 2222)

    def test_handle_default(self):
        self.assertEqual(self.klass().handle, None)

    def test_handle_explicit(self):
        self.assertEqual(self.klass(handle=1234).handle, 1234)

    def test_reply_to_default(self):
        self.assertEqual(self.klass().reply_to, None)

    def test_reply_to_explicit(self):
        self.assertEqual(self.klass(reply_to=8888).reply_to, 8888)

    def test_data_default(self):
        m = self.klass()
        self.assertEqual(m.data, b(''))
        self.assertIsInstance(m.data, mitogen.core.BytesType)

    def test_data_explicit(self):
        m = self.klass(data=b('asdf'))
        self.assertEqual(m.data, b('asdf'))
        self.assertIsInstance(m.data, mitogen.core.BytesType)

    def test_data_hates_unicode(self):
        self.assertRaises(Exception,
            lambda: self.klass(data=u'asdf'))


class PackTest(testlib.TestCase):
    klass = mitogen.core.Message

    def test_header_format_sanity(self):
        self.assertEqual(self.klass.HEADER_LEN,
                          struct.calcsize(self.klass.HEADER_FMT))

    def test_header_length_correct(self):
        s = self.klass(dst_id=123, handle=123).pack()
        self.assertEqual(len(s), self.klass.HEADER_LEN)

    def test_magic(self):
        s = self.klass(dst_id=123, handle=123).pack()
        magic, = struct.unpack('>h', s[:2])
        self.assertEqual(self.klass.HEADER_MAGIC, magic)

    def test_dst_id(self):
        s = self.klass(dst_id=123, handle=123).pack()
        dst_id, = struct.unpack('>L', s[2:6])
        self.assertEqual(123, dst_id)

    def test_src_id(self):
        s = self.klass(src_id=5432, dst_id=123, handle=123).pack()
        src_id, = struct.unpack('>L', s[6:10])
        self.assertEqual(5432, src_id)

    def test_auth_id(self):
        s = self.klass(auth_id=1919, src_id=5432, dst_id=123, handle=123).pack()
        auth_id, = struct.unpack('>L', s[10:14])
        self.assertEqual(1919, auth_id)

    def test_handle(self):
        s = self.klass(dst_id=123, handle=9999).pack()
        handle, = struct.unpack('>L', s[14:18])
        self.assertEqual(9999, handle)

    def test_reply_to(self):
        s = self.klass(dst_id=1231, handle=7777, reply_to=9132).pack()
        reply_to, = struct.unpack('>L', s[18:22])
        self.assertEqual(9132, reply_to)

    def test_data_length_empty(self):
        s = self.klass(dst_id=1231, handle=7777).pack()
        data_length, = struct.unpack('>L', s[22:26])
        self.assertEqual(0, data_length)

    def test_data_length_present(self):
        s = self.klass(dst_id=1231, handle=7777, data=b('hello')).pack()
        data_length, = struct.unpack('>L', s[22:26])
        self.assertEqual(5, data_length)

    def test_data_empty(self):
        s = self.klass(dst_id=1231, handle=7777).pack()
        data = s[26:]
        self.assertEqual(b(''), data)

    def test_data_present(self):
        s = self.klass(dst_id=11, handle=77, data=b('hello')).pack()
        data = s[26:]
        self.assertEqual(b('hello'), data)


class IsDeadTest(testlib.TestCase):
    klass = mitogen.core.Message

    def test_is_dead(self):
        msg = self.klass(reply_to=mitogen.core.IS_DEAD)
        self.assertTrue(msg.is_dead)

    def test_is_not_dead(self):
        msg = self.klass(reply_to=5555)
        self.assertFalse(msg.is_dead)


class DeadTest(testlib.TestCase):
    klass = mitogen.core.Message

    def test_no_reason(self):
        msg = self.klass.dead()
        self.assertEqual(msg.reply_to, mitogen.core.IS_DEAD)
        self.assertTrue(msg.is_dead)
        self.assertEqual(msg.data, b(''))

    def test_with_reason(self):
        msg = self.klass.dead(reason=u'oh no')
        self.assertEqual(msg.reply_to, mitogen.core.IS_DEAD)
        self.assertTrue(msg.is_dead)
        self.assertEqual(msg.data, b('oh no'))


class EvilObject(object):
    pass


class PickledTest(testlib.TestCase):
    # getting_started.html#rpc-serialization-rules
    klass = mitogen.core.Message

    def roundtrip(self, v, router=None):
        msg = self.klass.pickled(v)
        msg2 = self.klass(data=msg.data)
        msg2.router = router
        return msg2.unpickle()

    def test_bool(self):
        for b in True, False:
            self.assertEqual(b, self.roundtrip(b))

    @unittest.skipIf(condition=sys.version_info < (2, 6),
                      reason='bytearray missing on <2.6')
    def test_bytearray(self):
        ba = bytearray(b('123'))
        self.assertRaises(mitogen.core.StreamError,
            lambda: self.roundtrip(ba)
        )

    def test_bytes(self):
        by = b('123')
        self.assertEqual(by, self.roundtrip(by))

    def test_dict(self):
        d = {1: 2, u'a': 3, b('b'): 4, 'c': {}}
        roundtrip = self.roundtrip(d)
        self.assertEqual(d, roundtrip)
        self.assertIsInstance(roundtrip, dict)
        for k in d:
            self.assertIsInstance(roundtrip[k], type(d[k]))

    def test_int(self):
        self.assertEqual(123, self.klass.pickled(123).unpickle())

    def test_list(self):
        l = [1, u'b', b('c')]
        roundtrip = self.roundtrip(l)
        self.assertIsInstance(roundtrip, list)
        self.assertEqual(l, roundtrip)
        for k in range(len(l)):
            self.assertIsInstance(roundtrip[k], type(l[k]))

    @unittest.skipIf(condition=sys.version_info > (3, 0),
                      reason='long missing in >3.x')
    def test_long(self):
        l = long(0xffffffffffff)
        roundtrip = self.roundtrip(l)
        self.assertEqual(l, roundtrip)
        self.assertIsInstance(roundtrip, long)

    def test_tuple(self):
        l = (1, u'b', b('c'))
        roundtrip = self.roundtrip(l)
        self.assertEqual(l, roundtrip)
        self.assertIsInstance(roundtrip, tuple)
        for k in range(len(l)):
            self.assertIsInstance(roundtrip[k], type(l[k]))

    def test_unicode(self):
        u = u'abcd'
        roundtrip = self.roundtrip(u)
        self.assertEqual(u, roundtrip)
        self.assertIsInstance(roundtrip, mitogen.core.UnicodeType)

    #### custom types. see also: types_test.py, call_error_test.py

    # Python 3 pickle protocol 2 does weird stuff depending on whether an empty
    # or nonempty bytes is being serialized. For non-empty, it yields a
    # _codecs.encode() call. For empty, it yields a bytes() call.

    def test_blob_nonempty(self):
        v = mitogen.core.Blob(b('dave'))
        roundtrip = self.roundtrip(v)
        self.assertIsInstance(roundtrip, mitogen.core.Blob)
        self.assertEqual(b('dave'), roundtrip)

    def test_blob_empty(self):
        v = mitogen.core.Blob(b(''))
        roundtrip = self.roundtrip(v)
        self.assertIsInstance(roundtrip, mitogen.core.Blob)
        self.assertEqual(b(''), v)

    def test_secret_nonempty(self):
        s = mitogen.core.Secret(u'dave')
        roundtrip = self.roundtrip(s)
        self.assertIsInstance(roundtrip, mitogen.core.Secret)
        self.assertEqual(u'dave', roundtrip)

    def test_secret_empty(self):
        s = mitogen.core.Secret(u'')
        roundtrip = self.roundtrip(s)
        self.assertIsInstance(roundtrip, mitogen.core.Secret)
        self.assertEqual(u'', roundtrip)

    def test_call_error(self):
        ce = mitogen.core.CallError('nope')
        ce2 = self.assertRaises(mitogen.core.CallError,
            lambda: self.roundtrip(ce))
        self.assertEqual(ce.args[0], ce2.args[0])

    def test_context(self):
        router = mitogen.master.Router()
        try:
            c = router.context_by_id(1234)
            roundtrip = self.roundtrip(c)
            self.assertIsInstance(roundtrip, mitogen.core.Context)
            self.assertEqual(c.context_id, 1234)
        finally:
            router.broker.shutdown()
            router.broker.join()

    def test_sender(self):
        router = mitogen.master.Router()
        try:
            recv = mitogen.core.Receiver(router)
            sender = recv.to_sender()
            roundtrip = self.roundtrip(sender, router=router)
            self.assertIsInstance(roundtrip, mitogen.core.Sender)
            self.assertEqual(roundtrip.context.context_id, mitogen.context_id)
            self.assertEqual(roundtrip.dst_handle, sender.dst_handle)
        finally:
            router.broker.shutdown()
            router.broker.join()

    ####

    def test_custom_object_deserialization_fails(self):
        self.assertRaises(mitogen.core.StreamError,
            lambda: self.roundtrip(EvilObject())
        )


class ReplyTest(testlib.TestCase):
    # getting_started.html#rpc-serialization-rules
    klass = mitogen.core.Message

    def test_reply_calls_router_route(self):
        msg = self.klass(src_id=1234, reply_to=9191)
        router = mock.Mock()
        msg.reply(123, router=router)
        self.assertEqual(1, router.route.call_count)

    def test_reply_pickles_object(self):
        msg = self.klass(src_id=1234, reply_to=9191)
        router = mock.Mock()
        msg.reply(123, router=router)
        _, (reply,), _ = router.route.mock_calls[0]
        self.assertEqual(reply.dst_id, 1234)
        self.assertEqual(reply.unpickle(), 123)

    def test_reply_uses_preformatted_message(self):
        msg = self.klass(src_id=1234, reply_to=9191)
        router = mock.Mock()
        my_reply = mitogen.core.Message.pickled(4444)
        msg.reply(my_reply, router=router)
        _, (reply,), _ = router.route.mock_calls[0]
        self.assertIs(my_reply, reply)
        self.assertEqual(reply.dst_id, 1234)
        self.assertEqual(reply.unpickle(), 4444)

    def test_reply_sets_dst_id(self):
        msg = self.klass(src_id=1234, reply_to=9191)
        router = mock.Mock()
        msg.reply(123, router=router)
        _, (reply,), _ = router.route.mock_calls[0]
        self.assertEqual(reply.dst_id, 1234)

    def test_reply_sets_handle(self):
        msg = self.klass(src_id=1234, reply_to=9191)
        router = mock.Mock()
        msg.reply(123, router=router)
        _, (reply,), _ = router.route.mock_calls[0]
        self.assertEqual(reply.handle, 9191)


class UnpickleTest(testlib.TestCase):
    # mostly done by PickleTest, just check behaviour of parameters
    klass = mitogen.core.Message

    def test_throw(self):
        ce = mitogen.core.CallError('nope')
        m = self.klass.pickled(ce)
        ce2 = self.assertRaises(mitogen.core.CallError,
            lambda: m.unpickle())
        self.assertEqual(ce.args[0], ce2.args[0])

    def test_no_throw(self):
        ce = mitogen.core.CallError('nope')
        m = self.klass.pickled(ce)
        ce2 = m.unpickle(throw=False)
        self.assertEqual(ce.args[0], ce2.args[0])

    def test_throw_dead(self):
        m = self.klass.pickled('derp', reply_to=mitogen.core.IS_DEAD)
        self.assertRaises(mitogen.core.ChannelError,
            lambda: m.unpickle())

    def test_no_throw_dead(self):
        m = self.klass.pickled('derp', reply_to=mitogen.core.IS_DEAD)
        self.assertEqual('derp', m.unpickle(throw_dead=False))


class UnpickleCompatTest(testlib.TestCase):
    # try weird variations of pickles from different Python versions.
    klass = mitogen.core.Message

    def check(self, value, encoded, **kwargs):
        if isinstance(encoded, mitogen.core.UnicodeType):
            encoded = encoded.encode('latin1')
        m = self.klass(data=encoded)
        m.router = mitogen.master.Router()
        try:
            return m.unpickle(**kwargs)
        finally:
            m.router.broker.shutdown()
            m.router.broker.join()

    def test_py24_bytes(self):
        self.check('test',
           ('\x80\x02U\x04testq\x00.'))

    def test_py24_unicode(self):
        self.check(u'test',
           ('\x80\x02X\x04\x00\x00\x00testq\x00.'))

    def test_py24_int(self):
        self.check(123,
           ('\x80\x02K{.'))

    def test_py24_long(self):
        self.check(17592186044415,
           ('\x80\x02\x8a\x06\xff\xff\xff\xff\xff\x0f.'))

    def test_py24_dict(self):
        self.check({},
           ('\x80\x02}q\x00.'))

    def test_py24_tuple(self):
        self.check((1, 2, u'b'),
           ('\x80\x02K\x01K\x02X\x01\x00\x00\x00bq\x00\x87q\x01.'))

    def test_py24_bool(self):
        self.check(True,
           ('\x80\x02\x88.'))

    def test_py24_list(self):
        self.check([1, 2, u'b'],
           ('\x80\x02]q\x00(K\x01K\x02X\x01\x00\x00\x00bq\x01e.'))

    def test_py24_blob(self):
        self.check(mitogen.core.mitogen.core.Blob(b('bigblob')),
           ('\x80\x02cmitogen.core\nBlob\nq\x00U\x07bigblobq\x01\x85q\x02Rq\x03.'))

    def test_py24_secret(self):
        self.check(mitogen.core.Secret(u'mypassword'),
           ('\x80\x02cmitogen.core\nSecret\nq\x00X\n\x00\x00\x00mypasswordq\x01\x85q\x02Rq\x03.'))

    def test_py24_call_error(self):
        self.check(mitogen.core.CallError('big error'),
           ('\x80\x02cmitogen.core\n_unpickle_call_error\nq\x00X\t\x00\x00\x00big errorq\x01\x85q\x02R.'), throw=False)

    def test_py24_context(self):
        self.check(mitogen.core.Context(1234, None),
           ('\x80\x02cmitogen.core\n_unpickle_context\nq\x00M\xd2\x04N\x86q\x01Rq\x02.'))

    def test_py24_sender(self):
        self.check(mitogen.core.Sender(mitogen.core.Context(55555, None), 4444),
           ('\x80\x02cmitogen.core\n_unpickle_sender\nq\x00M\x03\xd9M\\\x11\x86q\x01Rq\x02.'))

    def test_py27_bytes(self):
        self.check(b('test'),
           ('\x80\x02U\x04testq\x01.'))

    def test_py27_unicode(self):
        self.check(u'test',
           ('\x80\x02X\x04\x00\x00\x00testq\x01.'))

    def test_py27_int(self):
        self.check(123,
           ('\x80\x02K{.'))

    def test_py27_long(self):
        self.check(17592186044415,
           ('\x80\x02\x8a\x06\xff\xff\xff\xff\xff\x0f.'))

    def test_py27_dict(self):
        self.check({},
           ('\x80\x02}q\x01.'))

    def test_py27_tuple(self):
        self.check((1, 2, u'b'),
           ('\x80\x02K\x01K\x02X\x01\x00\x00\x00b\x87q\x01.'))

    def test_py27_bool(self):
        self.check(True,
           ('\x80\x02\x88.'))

    def test_py27_list(self):
        self.check([1, 2, u'b'],
           ('\x80\x02]q\x01(K\x01K\x02X\x01\x00\x00\x00be.'))

    def test_py27_blob(self):
        self.check(mitogen.core.mitogen.core.Blob(b('bigblob')),
           ('\x80\x02cmitogen.core\nBlob\nq\x01U\x07bigblob\x85Rq\x02.'))

    def test_py27_secret(self):
        self.check(mitogen.core.Secret(u'mypassword'),
           ('\x80\x02cmitogen.core\nSecret\nq\x01X\n\x00\x00\x00mypassword\x85Rq\x02.'))

    def test_py27_call_error(self):
        self.check(mitogen.core.CallError(u'big error',),
           ('\x80\x02cmitogen.core\n_unpickle_call_error\nq\x01X\t\x00\x00\x00big errorq\x02\x85Rq\x03.'), throw=False)

    def test_py27_context(self):
        self.check(mitogen.core.Context(1234, None),
           ('\x80\x02cmitogen.core\n_unpickle_context\nq\x01M\xd2\x04N\x86Rq\x02.'))

    def test_py27_sender(self):
        self.check(mitogen.core.Sender(mitogen.core.Context(55555, None), 4444),
           ('\x80\x02cmitogen.core\n_unpickle_sender\nq\x01M\x03\xd9M\\\x11\x86Rq\x02.'))

    def test_py36_bytes(self):
        self.check(b('test'),
           ('\x80\x02c_codecs\nencode\nq\x00X\x04\x00\x00\x00testq\x01X\x06\x00\x00\x00latin1q\x02\x86q\x03Rq\x04.'))

    def test_py36_unicode(self):
        self.check('test',
           ('\x80\x02X\x04\x00\x00\x00testq\x00.'))

    def test_py36_int(self):
        self.check(123,
           ('\x80\x02K{.'))

    def test_py36_long(self):
        self.check(17592186044415,
           ('\x80\x02\x8a\x06\xff\xff\xff\xff\xff\x0f.'))

    def test_py36_dict(self):
        self.check({},
           ('\x80\x02}q\x00.'))

    def test_py36_tuple(self):
        self.check((1, 2, u'b'),
           ('\x80\x02K\x01K\x02X\x01\x00\x00\x00bq\x00\x87q\x01.'))

    def test_py36_bool(self):
        self.check(True,
           ('\x80\x02\x88.'))

    def test_py36_list(self):
        self.check([1, 2, u'b'],
           ('\x80\x02]q\x00(K\x01K\x02X\x01\x00\x00\x00bq\x01e.'))

    def test_py36_blob(self):
        self.check(mitogen.core.mitogen.core.Blob(b('bigblob')),
           ('\x80\x02cmitogen.core\nBlob\nq\x00c_codecs\nencode\nq\x01X\x07\x00\x00\x00bigblobq\x02X\x06\x00\x00\x00latin1q\x03\x86q\x04Rq\x05\x85q\x06Rq\x07.'))

    def test_py36_secret(self):
        self.check(mitogen.core.Secret('mypassword'),
           ('\x80\x02cmitogen.core\nSecret\nq\x00X\n\x00\x00\x00mypasswordq\x01\x85q\x02Rq\x03.'))

    def test_py36_call_error(self):
        self.check(mitogen.core.CallError('big error'),
           ('\x80\x02cmitogen.core\n_unpickle_call_error\nq\x00X\t\x00\x00\x00big errorq\x01\x85q\x02Rq\x03.'), throw=False)

    def test_py36_context(self):
        self.check(mitogen.core.Context(1234, None),
           ('\x80\x02cmitogen.core\n_unpickle_context\nq\x00M\xd2\x04N\x86q\x01Rq\x02.'))

    def test_py36_sender(self):
        self.check(mitogen.core.Sender(mitogen.core.Context(55555, None), 4444),
           ('\x80\x02cmitogen.core\n_unpickle_sender\nq\x00M\x03\xd9M\\\x11\x86q\x01Rq\x02.'))


class ReprTest(testlib.TestCase):
    klass = mitogen.core.Message

    def test_repr(self):
        # doesn't crash
        repr(self.klass.pickled('test'))
