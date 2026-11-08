from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import logging
from pathlib import Path
import sys
from threading import Event
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.progress import TerminalProgress, quiet_model_output


class TerminalBuffer(StringIO):
    def __init__(self):
        super().__init__()
        self.animated = Event()
        self.frames = 0

    def isatty(self):
        return True

    def write(self, text):
        result = super().write(text)
        if text.startswith('\r') and text[1:2] in '/-\\|':
            self.frames += 1
            if self.frames >= 3:
                self.animated.set()
        return result


class ProgressTests(unittest.TestCase):
    def test_spinner_animates_independently_and_clears_before_iteration(self):
        stream = TerminalBuffer()
        with TerminalProgress(stream, interval=.01) as display:
            display.print_status('Chargement des données…')
            self.assertTrue(stream.animated.wait(1), 'Le spinner doit avancer pendant une opération bloquante.')
            display.print_status('Features…')
            self.assertNotIn('\n', stream.getvalue())
            display.iteration(1, 2, 'SARIMAXRegressor', 2.34, .12)
            self.assertIsNone(display._thread)
        self.assertEqual(stream.getvalue().count('\n'), 1)
        self.assertTrue(stream.getvalue().endswith(
            '[1/2] [SARIMAXRegressor] Fit time elapsed: 2.34s - Pred time elapsed: 0.12s\n'))

    def test_exception_and_keyboard_interrupt_stop_spinner(self):
        for exception in (RuntimeError('échec'), KeyboardInterrupt()):
            with self.subTest(exception=type(exception).__name__):
                stream = TerminalBuffer()
                display = TerminalProgress(stream)
                with self.assertRaises(type(exception)):
                    with display:
                        display.print_status('Préparation…')
                        worker = display._thread
                        raise exception
                self.assertFalse(worker.is_alive())
                self.assertEqual(display._width, 0)
                display.stop()  # Nettoyage réentrant, sans nouvelle sortie.

    def test_redirected_output_has_no_spinner_control_characters(self):
        stream = StringIO()
        with TerminalProgress(stream) as display:
            display.print_status('Imports…')
            display.print_status('Features…')
            display.iteration(1, 1, 'KumoTabularRegressor', 1., .2)
            display.write('Résultats')
        self.assertEqual(stream.getvalue(),
            '[1/1] [KumoTabularRegressor] Fit time elapsed: 1.00s - Pred time elapsed: 0.20s\nRésultats\n')

    def test_library_output_is_silent_and_streams_restored_after_failure(self):
        output, errors = StringIO(), StringIO()
        previous = logging.root.manager.disable
        with redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaisesRegex(RuntimeError, 'fit impossible'):
                with quiet_model_output():
                    print('Progression externe')
                    print('Barre de téléchargement', file=sys.stderr)
                    logging.warning('Avertissement externe')
                    raise RuntimeError('fit impossible')
            print('Sortie restaurée')
        self.assertEqual(output.getvalue(), 'Sortie restaurée\n')
        self.assertEqual(errors.getvalue(), '')
        self.assertEqual(logging.root.manager.disable, previous)


if __name__ == '__main__':
    unittest.main()
