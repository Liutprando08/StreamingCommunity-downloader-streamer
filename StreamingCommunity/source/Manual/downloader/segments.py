# 19.05.25

import os
import time
import signal
import logging
import threading


# External libraries
from rich.console import Console
from concurrent.futures import ThreadPoolExecutor, as_completed


# Internal utilities
from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.http_client import create_client, get_headers, get_userAgent
from StreamingCommunity.core.ui.bar_manager import DownloadBarManager
from StreamingCommunity.source.utils.tracker import download_tracker


# Logic
from ..utils.file_size import format_size


# Variable
logger = logging.getLogger(__name__)
console = Console()
failed_segments = set()
failed_segments_lock = threading.Lock()
shutdown_flag = threading.Event()
TIMEOUT = config_manager.config.get_int('REQUESTS', 'timeout')
MAX_WORKERS = config_manager.config.get_int('DOWNLOAD', 'thread_count')
MAX_RETRIES = config_manager.config.get_int('REQUESTS', 'max_retry')


class SegmentDownloader:
    def __init__(self, headers=None, max_workers=MAX_WORKERS, max_retries=MAX_RETRIES, download_id=None):
        self.headers = headers or get_headers()
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.download_id = download_id
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        shutdown_flag.set()
        raise KeyboardInterrupt("Download cancelled by user")
    
    def is_cancelled(self):
        """Check if download should be cancelled (signal or GUI stop)"""
        return shutdown_flag.is_set() or (self.download_id and download_tracker.is_stopped(self.download_id))
    
    def download_segment(self, segment):
        if self.is_cancelled():
            return False
        
        with failed_segments_lock:
            if segment.number in failed_segments:
                logger.info(f"Skipping segment {segment.number} (globally failed)")
                return False
        
        for attempt in range(1, self.max_retries + 1):
            if self.is_cancelled():
                return False
            
            try:
                # Generate new User-Agent for each segment request
                segment_headers = self.headers.copy()
                segment_headers['User-Agent'] = get_userAgent()
                with create_client(headers=segment_headers, timeout=TIMEOUT, follow_redirects=True) as client:
                    response = client.get(segment.url)
                    response.raise_for_status()
                    
                    content = response.content
                    segment.size = len(content)
                    segment.content = content
                    segment.downloaded = True
                    
                    logger.debug(f"Downloaded segment {segment.number} ({format_size(segment.size)})")
                    return True
                    
            except Exception as e:
                logger.warning(f"Segment {segment.number} failed (attempt {attempt}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries:
                    time.sleep(1 * attempt)
                else:
                    logger.error(f"Segment {segment.number} permanently failed")
                    with failed_segments_lock:
                        failed_segments.add(segment.number)
                    return False
        
        return False
    
    def download_all(self, segments, output_dir, description="segments", stream_type="media", language="und", resolution="", encryption_method=None, key_data=None, iv=None, decryptor=None):
        os.makedirs(output_dir, exist_ok=True)
        
        with failed_segments_lock:
            failed_segments.clear()

        total_segments = len(segments)
        total_size = 0
        downloaded_count = 0
        failed_count = 0
        start_time = time.time()
        
        # Format description based on stream type
        if stream_type == "video":
            display_desc = f"[red]Video {resolution}[/red]" if resolution else "[red]Video[/red]"
        elif stream_type == "audio":
            display_desc = f"[green]Audio {language}[/green]" if language else "[green]Audio[/green]"
        elif stream_type == "subtitle":
            display_desc = f"[yellow]Subtitle {language}[/yellow]" if language else "[yellow]Subtitle[/yellow]"
        else:
            display_desc = description
        
        # Unified progress bar manager (Rich in CLI, null-context in GUI)
        with DownloadBarManager(self.download_id) as bar_mgr:
            if bar_mgr.progress is not None:
                bar_mgr.tasks["segments"] = bar_mgr.progress.add_task(
                    display_desc,
                    total=100,
                    segment="0/0",
                    speed="0 MB/s",
                    size="0 MB / ? MB",
                )
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self.download_segment, seg): seg for seg in segments}
                
                for future in as_completed(futures):
                    if self.is_cancelled():
                        logger.info("Download interrupted by user")
                        executor.shutdown(wait=False, cancel_futures=True)
                        return False
                    
                    segment = futures[future]
                    
                    try:
                        success = future.result()
                        if success:
                            downloaded_count += 1
                            total_size += segment.size
                            
                            if segment.type == 'init':
                                filename = 'init.m4s'
                            else:
                                filename = f"seg_{segment.number:05d}.m4s"
                            
                            # Decrypt if needed
                            if encryption_method == 'AES-128' and key_data and iv and decryptor:
                                encrypted_path = os.path.join(output_dir, f"encrypted_{filename}")
                                decrypted_path = os.path.join(output_dir, filename)
                                
                                with open(encrypted_path, 'wb') as f:
                                    f.write(segment.content)
                                
                                if decryptor.decrypt_hls_segment(encrypted_path, key_data, iv, decrypted_path):
                                    os.unlink(encrypted_path)
                                else:
                                    os.rename(encrypted_path, decrypted_path)
                            else:
                                output_path = os.path.join(output_dir, filename)
                                with open(output_path, 'wb') as f:
                                    f.write(segment.content)
                            
                            elapsed = time.time() - start_time
                            speed = total_size / elapsed if elapsed > 0 else 0
                            progress_percent = (downloaded_count / total_segments * 100) if total_segments > 0 else 0
                            speed_str = f"{format_size(speed)}/s"
                            size_str = f"{format_size(total_size)} / {format_size(total_size * total_segments / max(downloaded_count, 1))}"
                            segments_str = f"{downloaded_count}/{total_segments}"
                            
                            bar_mgr.handle_progress_line(
                                {
                                    "task_key": description,
                                    "label": display_desc,
                                    "pct": progress_percent,
                                    "speed": speed_str,
                                    "size": size_str,
                                    "segments": segments_str,
                                }
                            )
                        else:
                            failed_count += 1
                            bar_mgr.handle_progress_line(
                                {
                                    "task_key": description,
                                    "pct": ((downloaded_count + failed_count) / total_segments * 100) if total_segments > 0 else 0,
                                }
                            )
                    
                    except Exception as e:
                        logger.error(f"Error downloading segment {segment.number}: {e}")
                        failed_count += 1
                        bar_mgr.handle_progress_line(
                            {
                                "task_key": description,
                                "pct": ((downloaded_count + failed_count) / total_segments * 100) if total_segments > 0 else 0,
                            }
                        )
        
        elapsed = time.time() - start_time
        
        if failed_count > 0:
            console.print(f"[yellow]{failed_count} segments failed.")
        
        return failed_count == 0