# 19.05.25

import os
import logging


# External libraries
from rich.console import Console


# Variable
logger = logging.getLogger(__name__)
console = Console()


class FileMerger:
    @staticmethod
    def merge(segment_dir, output_file):
        try:
            init_file = os.path.join(segment_dir, 'init.m4s')

            # Ordinamento NUMERICO per numero di segmento
            segments = []
            for f in os.listdir(segment_dir):
                if f.startswith('seg_') and f.endswith('.m4s'):
                    try:
                        number = int(f[len('seg_'):-len('.m4s')])
                    except ValueError:
                        continue
                    segments.append((number, os.path.join(segment_dir, f)))

            segments.sort(key=lambda item: item[0])

            if not segments:
                console.print("[red]Merge failed: no segments found.")
                return False

            # Verifica di continuita': i numeri devono essere contigui.
            # Un segmento mancante = buco nella timeline = desync audio/video.
            expected = segments[0][0]
            for number, _ in segments:
                if number != expected:
                    console.print(f"[red]Merge failed: missing segment {expected} (got {number}).")
                    return False
                expected += 1

            with open(output_file, 'wb') as outfile:
                if os.path.exists(init_file):
                    with open(init_file, 'rb') as f:
                        outfile.write(f.read())

                for _, seg_file in segments:
                    with open(seg_file, 'rb') as f:
                        outfile.write(f.read())
            return True

        except Exception as e:
            console.print(f"[red]Merge failed: {e}.")
            return False
