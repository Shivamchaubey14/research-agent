"""Tests for the agent's progress events and emitters (worker/agent/events.py)."""
import unittest

from worker.agent import events
from worker.agent.events import (
    CallbackEmitter,
    LoggingEmitter,
    ProgressEmitter,
    ProgressEvent,
)


class ProgressEventTests(unittest.TestCase):
    def test_data_defaults_to_an_empty_dict(self):
        event = ProgressEvent(kind=events.PLAN, message="planning")
        self.assertEqual(event.data, {})

    def test_each_event_gets_its_own_data_dict(self):
        a = ProgressEvent(kind=events.SEARCH, message="a")
        b = ProgressEvent(kind=events.SEARCH, message="b")
        a.data["q"] = 1
        self.assertEqual(b.data, {})

    def test_known_event_kinds_are_distinct(self):
        kinds = [
            events.PLAN, events.STATUS, events.SEARCH, events.OBSERVATION,
            events.REASONING, events.VERIFICATION, events.REPORT, events.ERROR,
        ]
        self.assertEqual(len(kinds), len(set(kinds)))


class EmitterTests(unittest.TestCase):
    def test_callback_emitter_forwards_the_event(self):
        seen = []
        emitter = CallbackEmitter(seen.append)
        event = ProgressEvent(kind=events.REPORT, message="done", data={"n": 1})
        emitter.emit(event)
        self.assertEqual(seen, [event])

    def test_base_emitter_is_abstract(self):
        with self.assertRaises(NotImplementedError):
            ProgressEmitter().emit(ProgressEvent(kind=events.STATUS, message="x"))

    def test_logging_emitter_writes_a_record(self):
        emitter = LoggingEmitter()
        with self.assertLogs("worker.agent", level="INFO") as captured:
            emitter.emit(ProgressEvent(kind=events.STATUS, message="running"))
        self.assertTrue(any("running" in line for line in captured.output))
        self.assertTrue(any("agent.status" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
