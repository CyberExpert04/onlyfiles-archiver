import asyncio
import aiohttp
import os
import re
import time
from datetime import datetime
from tqdm import tqdm

INPUT_FILE = "onlyfiles.txt"
BASE_DOWNLOAD_FOLDER = "downloads"
ERROR_LOG = "errors.txt"

MAX_CONCURRENT_DOWNLOADS = 15
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=120)

ID_PATTERN = re.compile(r"([a-f0-9]{32})")


def parse_urls(input_file: str) -> list[str]:
    with open(input_file, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def unwrap_pillowcase_url(url: str) -> str | None:
    if "pillowcase.su/f/" in url:
        return url

    match = re.search(r"(https://pillowcase\.su/f/[a-f0-9]{32})", url)
    if match:
        return match.group(1)

    return None


def log_error(filename: str, url: str, reason: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{filename}\t{url}\t{reason}\n")


async def download_file(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    url: str,
    output_folder: str,
    progress: tqdm,
):
    async with semaphore:
        filename = "unknown"

        try:
            real_url = unwrap_pillowcase_url(url)
            if not real_url:
                log_error(filename, url, "No pillowcase link found")
                return

            match = ID_PATTERN.search(real_url)
            if not match:
                log_error(filename, url, "No file ID found")
                return

            identifier = match.group(1)
            download_url = f"https://api.pillows.su/api/download/{identifier}"

            async with session.get(download_url) as resp:
                resp.raise_for_status()

                cd = resp.headers.get("content-disposition")
                if cd and "filename=" in cd:
                    filename = cd.split("filename=")[-1].strip().strip('"')
                else:
                    filename = f"{identifier}.bin"

                filepath = os.path.join(output_folder, filename)

                with open(filepath, "wb") as f_out:
                    async for chunk in resp.content.iter_chunked(8192):
                        f_out.write(chunk)

        except Exception as e:
            log_error(filename, url, str(e))

        finally:
            progress.update(1)


async def main():
    urls = parse_urls(INPUT_FILE)
    total_files = len(urls)

    if total_files == 0:
        print("No URLs found.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_folder = os.path.join(BASE_DOWNLOAD_FOLDER, timestamp)
    os.makedirs(output_folder, exist_ok=True)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    start_time = time.monotonic()

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        with tqdm(
            total=total_files,
            desc="Downloading",
            unit="file",
            dynamic_ncols=True,
        ) as progress:
            tasks = [
                download_file(
                    session=session,
                    semaphore=semaphore,
                    url=url,
                    output_folder=output_folder,
                    progress=progress,
                )
                for url in urls
            ]

            await asyncio.gather(*tasks)

    elapsed = time.monotonic() - start_time
    print(f"\n✅ All done!")
    print(f"📁 Files saved in: {output_folder}")
    print(f"⏱ Total runtime: {elapsed:.2f} seconds")

    if os.path.exists(ERROR_LOG):
        print(f"⚠ Errors logged to: {ERROR_LOG}")


if __name__ == "__main__":
    asyncio.run(main())
