# pylint: disable=protected-access, c-extension-no-member, too-few-public-methods
"""
Tests for shillelagh.backends.apsw.db.
"""
import datetime
from typing import Any, List, NoReturn, Tuple
from unittest import mock

import apsw
import pytest
from pytest_mock import MockerFixture

from shillelagh.backends.apsw.db import connect, convert_binding
from shillelagh.exceptions import InterfaceError, NotSupportedError, ProgrammingError
from shillelagh.fields import Float, Integer, String

from ...fakes import FakeAdapter, FakeEntryPoint


def test_connect(mocker: MockerFixture) -> None:
    """
    Test ``connect``.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    assert cursor.rowcount == -1

    cursor.execute(
        """INSERT INTO "dummy://" (age, name, pets) VALUES (6, 'Billy', 1)""",
    )
    # assert cursor.rowcount == 1
    cursor.execute("""DELETE FROM "dummy://" WHERE name = 'Billy'""")
    # assert cursor.rowcount == 1

    cursor.execute('SELECT * FROM "dummy://"')
    assert cursor.fetchall() == [(20.0, "Alice", 0), (23.0, "Bob", 3)]
    assert cursor.rowcount == 2

    cursor.execute('SELECT * FROM "dummy://"')
    assert cursor.fetchone() == (20.0, "Alice", 0)
    assert cursor.rowcount == 2
    assert cursor.fetchone() == (23.0, "Bob", 3)
    assert cursor.rowcount == 2
    assert cursor.fetchone() is None

    cursor.execute('SELECT * FROM "dummy://" WHERE age > 21')
    assert cursor.fetchone() == (23.0, "Bob", 3)
    assert cursor.rowcount == 1
    assert cursor.fetchone() is None

    cursor.execute('SELECT * FROM "dummy://"')
    assert cursor.fetchmany() == [(20.0, "Alice", 0)]
    assert cursor.fetchmany(1000) == [(23.0, "Bob", 3)]
    assert cursor.fetchall() == []
    assert cursor.rowcount == 2


def test_connect_schema_prefix(mocker: MockerFixture) -> None:
    """
    Test querying a table with the schema.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    cursor.execute('SELECT * FROM main."dummy://"')
    assert cursor.fetchmany() == [(20.0, "Alice", 0)]
    assert cursor.fetchmany(1000) == [(23.0, "Bob", 3)]
    assert cursor.fetchall() == []
    assert cursor.rowcount == 2


def test_connect_adapter_kwargs(mocker: MockerFixture) -> None:
    """
    Test that ``adapter_kwargs`` are passed to the adapter.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )
    connection = mocker.patch("shillelagh.backends.apsw.db.Connection")

    connect(
        ":memory:",
        ["dummy"],
        isolation_level="IMMEDIATE",
        adapter_kwargs={"dummy": {"foo": "bar"}},
    )
    connection.assert_called_with(
        ":memory:",
        [FakeAdapter],
        {"fakeadapter": {"foo": "bar"}},
        "IMMEDIATE",
    )


def test_conect_safe(mocker: MockerFixture) -> None:
    """
    Test the safe option.
    """

    class FakeAdapter1(FakeAdapter):
        """
        A safe adapter.
        """

        safe = True

    class FakeAdapter2(FakeAdapter):
        """
        An unsafe adapter.
        """

        safe = False

    class FakeAdapter3(FakeAdapter):
        """
        Another unsafe adapter.
        """

        safe = False

    entry_points = [
        FakeEntryPoint("one", FakeAdapter1),
        FakeEntryPoint("two", FakeAdapter2),
        FakeEntryPoint("three", FakeAdapter3),
    ]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )
    # pylint: disable=invalid-name
    db_Connection = mocker.patch("shillelagh.backends.apsw.db.Connection")

    # if we don't specify adapters we should get all
    connect(":memory:")
    db_Connection.assert_called_with(
        ":memory:",
        [FakeAdapter1, FakeAdapter2, FakeAdapter3],
        {},
        None,
    )

    connect(":memory:", ["two"])
    db_Connection.assert_called_with(
        ":memory:",
        [FakeAdapter2],
        {},
        None,
    )

    # in safe mode we need to specify adapters
    connect(":memory:", safe=True)
    db_Connection.assert_called_with(
        ":memory:",
        [],
        {},
        None,
    )

    # in safe mode only safe adapters are returned
    connect(":memory:", ["one", "two", "three"], safe=True)
    db_Connection.assert_called_with(
        ":memory:",
        [FakeAdapter1],
        {},
        None,
    )

    # prevent repeated names, in case anyone registers a malicious adapter
    entry_points = [
        FakeEntryPoint("one", FakeAdapter1),
        FakeEntryPoint("one", FakeAdapter2),
    ]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )
    with pytest.raises(InterfaceError) as excinfo:
        connect(":memory:", ["one"], safe=True)
    assert str(excinfo.value) == "Repeated adapter names found: one"


def test_execute_with_native_parameters(mocker: MockerFixture) -> None:
    """
    Test passing native types to the cursor.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    cursor.execute(
        'SELECT * FROM "dummy://" WHERE name = ?',
        (datetime.datetime.now(),),
    )
    assert cursor.fetchall() == []
    assert cursor.rowcount == 0


def test_check_closed() -> None:
    """
    Test trying to use cursor/connection after closing them.
    """
    connection = connect(":memory:", isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    cursor.close()
    with pytest.raises(ProgrammingError) as excinfo:
        cursor.close()
    assert str(excinfo.value) == "Cursor already closed"

    connection.close()
    with pytest.raises(ProgrammingError) as excinfo:
        connection.close()
    assert str(excinfo.value) == "Connection already closed"


def test_check_result(mocker: MockerFixture) -> None:
    """
    Test exception raised when fetching results before query.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")
    cursor = connection.cursor()
    with pytest.raises(ProgrammingError) as excinfo:
        cursor.fetchall()

    assert str(excinfo.value) == "Called before ``execute``"


def test_check_invalid_syntax() -> None:
    """
    Test exception raised on syntax error.
    """
    connection = connect(":memory:", isolation_level="IMMEDIATE")
    with pytest.raises(ProgrammingError) as excinfo:
        connection.execute("SELLLLECT 1")
    assert str(excinfo.value) == 'SQLError: near "SELLLLECT": syntax error'


def test_unsupported_table() -> None:
    """
    Test exception raised on unsupported tables.
    """
    connection = connect(":memory:", isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    with pytest.raises(ProgrammingError) as excinfo:
        cursor.execute('SELECT * FROM "dummy://"')
    assert str(excinfo.value) == "Unsupported table: dummy://"


def test_description(mocker: MockerFixture) -> None:
    """
    Test cursor description.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    assert cursor.description is None
    cursor.execute(
        """INSERT INTO "dummy://" (age, name, pets) VALUES (6, 'Billy', 1)""",
    )
    assert cursor.description is None

    cursor.execute('SELECT * FROM "dummy://"')
    assert cursor.description == [
        ("age", Float, None, None, None, None, True),
        ("name", String, None, None, None, None, True),
        ("pets", Integer, None, None, None, None, True),
    ]


def test_execute_many(mocker: MockerFixture) -> None:
    """
    Test ``execute_many``.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")
    cursor = connection.cursor()

    items: List[Tuple[Any, ...]] = [(6, "Billy", 1), (7, "Timmy", 2)]
    with pytest.raises(NotSupportedError) as excinfo:
        cursor.executemany(
            """INSERT INTO "dummy://" (age, name, pets) VALUES (?, ?, ?)""",
            items,
        )
    assert (
        str(excinfo.value)
        == "``executemany`` is not supported, use ``execute`` instead"
    )


def test_setsize() -> None:
    """
    Test ``setinputsizes`` and ``setoutputsizes``.
    """
    connection = connect(":memory:", isolation_level="IMMEDIATE")
    cursor = connection.cursor()
    cursor.setinputsizes(100)
    cursor.setoutputsizes(100)


def test_close_connection(mocker: MockerFixture) -> None:
    """
    Testing closing a connection.
    """
    connection = connect(":memory:", isolation_level="IMMEDIATE")

    cursor1 = mocker.MagicMock()
    cursor1.closed = True
    cursor2 = mocker.MagicMock()
    cursor2.closed = False
    connection.cursors.extend([cursor1, cursor2])

    connection.close()

    cursor1.close.assert_not_called()
    cursor2.close.assert_called()


def test_transaction(mocker: MockerFixture) -> None:
    """
    Test transactions.
    """
    entry_points = [FakeEntryPoint("dummy", FakeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], isolation_level="IMMEDIATE")

    cursor = connection.cursor()
    cursor._cursor = mock.MagicMock()
    cursor._cursor.execute.side_effect = [
        "",
        apsw.SQLError("SQLError: no such table: dummy://"),
        "",
        "",
        "",
        "",
        "",
        "",
    ]

    assert not cursor.in_transaction
    connection.commit()
    cursor._cursor.execute.assert_not_called()

    cursor.execute('SELECT 1 FROM "dummy://"')
    assert cursor.in_transaction
    cursor._cursor.execute.assert_has_calls(
        [
            mock.call("BEGIN IMMEDIATE"),
            mock.call('SELECT 1 FROM "dummy://"', None),
            mock.call('CREATE VIRTUAL TABLE "dummy://" USING FakeAdapter()'),
            mock.call('SELECT 1 FROM "dummy://"', None),
        ],
    )

    connection.rollback()
    assert not cursor.in_transaction
    cursor.execute("SELECT 2")
    assert cursor.in_transaction
    cursor._cursor.execute.assert_has_calls(
        [
            mock.call("BEGIN IMMEDIATE"),
            mock.call('SELECT 1 FROM "dummy://"', None),
            mock.call('CREATE VIRTUAL TABLE "dummy://" USING FakeAdapter()'),
            mock.call('SELECT 1 FROM "dummy://"', None),
            mock.call("ROLLBACK"),
            mock.call("BEGIN IMMEDIATE"),
            mock.call("SELECT 2", None),
        ],
    )

    connection.commit()
    assert not cursor.in_transaction
    cursor._cursor.execute.assert_has_calls(
        [
            mock.call("BEGIN IMMEDIATE"),
            mock.call('SELECT 1 FROM "dummy://"', None),
            mock.call('CREATE VIRTUAL TABLE "dummy://" USING FakeAdapter()'),
            mock.call('SELECT 1 FROM "dummy://"', None),
            mock.call("ROLLBACK"),
            mock.call("BEGIN IMMEDIATE"),
            mock.call("SELECT 2", None),
            mock.call("COMMIT"),
        ],
    )

    cursor._cursor.reset_mock()
    connection.rollback()
    cursor._cursor.execute.assert_not_called()


def test_connection_context_manager() -> None:
    """
    Test that connection can be used as context manager.
    """
    with connect(":memory:", isolation_level="IMMEDIATE") as connection:
        cursor = connection.cursor()
        cursor._cursor = mock.MagicMock()
        cursor.execute("SELECT 2")

    cursor._cursor.execute.assert_has_calls(
        [
            mock.call("BEGIN IMMEDIATE"),
            mock.call("SELECT 2", None),
            mock.call("COMMIT"),
        ],
    )


def test_connect_safe(mocker: MockerFixture) -> None:
    """
    Test the safe connection.
    """

    class UnsafeAdapter(FakeAdapter):

        """
        A safe adapter.
        """

        safe = False

    entry_points = [FakeEntryPoint("dummy", UnsafeAdapter)]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:", ["dummy"], safe=True, isolation_level="IMMEDIATE")
    assert connection._adapters == []


def test_connect_unmet_dependency(mocker: MockerFixture) -> None:
    """
    Test that we ignore adapters with unmet dependencies.
    """

    class ProblematicEntryPoint(FakeEntryPoint):
        """
        A problematic entry point.
        """

        def load(self) -> NoReturn:
            raise ModuleNotFoundError("Couldn't find some dep")

    class AnotherProblematicEntryPoint(FakeEntryPoint):
        """
        Another problematic entry point.
        """

        def load(self) -> NoReturn:
            raise ImportError("Couldn't find some dep")

    entry_points = [
        FakeEntryPoint("dummy", FakeAdapter),
        ProblematicEntryPoint("trouble", FakeAdapter),
        AnotherProblematicEntryPoint("more_trouble", FakeAdapter),
    ]
    mocker.patch(
        "shillelagh.backends.apsw.db.iter_entry_points",
        return_value=entry_points,
    )

    connection = connect(":memory:")
    assert connection._adapters == [FakeAdapter]


def test_convert_binding() -> None:
    """
    Test conversion to SQLite types.
    """
    assert convert_binding(1) == 1
    assert convert_binding(1.0) == 1.0
    assert convert_binding("test") == "test"
    assert convert_binding(None) is None
    assert convert_binding(datetime.datetime(2021, 1, 1)) == "2021-01-01T00:00:00"
    assert convert_binding(datetime.date(2021, 1, 1)) == "2021-01-01"
    assert convert_binding(datetime.time(12, 0, 0)) == "12:00:00"
    assert (
        convert_binding(datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc))
        == "2021-01-01T00:00:00+00:00"
    )
    assert (
        convert_binding(datetime.time(12, 0, 0, tzinfo=datetime.timezone.utc))
        == "12:00:00+00:00"
    )
    assert convert_binding(True) == 1
    assert convert_binding(False) == 0
    assert convert_binding({}) == "{}"
