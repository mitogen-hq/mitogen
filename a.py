
import mitogen.core
import mitogen.error


@mitogen.main()
def main(router):
    ve = ValueError('eep')
    ke = KeyError('eep')

    cve = mitogen.core.CallError.from_exception(ve)
    kve = mitogen.core.CallError.from_exception(ke)

    print([cve, type(cve)])
    print([kve])

    mve = mitogen.error.match(ValueError)
    assert isinstance(cve, mve)
    assert not isinstance(kve, mve)

    print
    print
    print
    print


    try:
        raise cve
    except mve:
        pass

