from argparse import ArgumentParser as _ArgumentParser
from asyncio import (
	get_event_loop as _get_event_loop, gather as _gather, run as _run,
	sleep as _sleep, Event as _Event
)
from binascii import hexlify as _hexlify, unhexlify as _unhexlify
from atexit import register as _register
from sys import exit as _exit, stdin as _stdin, stdout as _stdout
from signal import signal as _signal, SIGINT as _SIGINT, SIGTERM as _SIGTERM
from aioserial import AioSerial as _AioSerial
from serial.tools.list_ports import comports as _comports

async def input_async(prompt: object = ""):
	loop = _get_event_loop()
	await loop.run_in_executor(None, _stdout.write, prompt)
	return (await loop.run_in_executor(None, _stdin.readline)).rstrip("\n")

def format_hex(data: bytes, chunk_size: int = 16):
	"""Format data bytes in hexadecimal-ascii format

	:param data: Data bytes.
	:return: Formatted string.
	"""
	hex_size = chunk_size * 3 - 1
	return "\n".join(f"""{_hexlify(c, ' ').decode('ascii') : <{
		f'{hex_size}'}} | {''.join(
			chr(b) if 32 <= b <= 126 else
			'\033[7m \033[27m' for b in c
	)}""" for c in (data[i : i + chunk_size] for i in range(
		0, len(data), chunk_size
	)))

def list_ports():
	"""List available serial ports.

	:return: Serial ports.
	"""
	return (port.device for port in _comports())

def connect_port(port: str, baudrate: int = 9600, timeout: float = 0.1):
	"""Connect to a serial port.

	:param port: The port.
	:param baudrate: Baudrate.
	:param timeout: Timeout for reading data.
	:return: ``aioserial.AioSerial`` instance pn success.
	"""
	return _AioSerial(port, baudrate, timeout = timeout)

async def serial_read_handler(
	serial: _AioSerial, stop_event: _Event, hex_mode = False
):
	"""Read and print serial port data.

	:param serial: ``aioserial.AioSerial`` instance.
	:param stop_event: Event for stopping the loop.
	:param hex_mode: Whether to print in hexadecimal form.
	"""
	formatter = format_hex if hex_mode else lambda d: f"{d}"[2:-1]
	data = b""
	while not stop_event.is_set():
		await _sleep(0)
		if serial.in_waiting:
			continue
		# print received data if any
		try:
			data = await serial.readline_async()
			if data:
				_stdout.write(f"\r{formatter(data)}\n")
				_stdout.write(">>> ")
		except Exception as e:
			_stdout.write(f"error while receiving: {e}\n")
		_stdout.flush()

async def serial_send_handler(
	serial: _AioSerial, stop_event: _Event, hex_mode = False
):
	"""Send serial port data.

	:param serial: ``aioserial.AioSerial`` instance.
	:param stop_event: Event for stopping the loop.
	:param hex_mode: Whether to send in hexadecimal form.
	"""
	formatter = (
		(lambda d: _unhexlify("".join(d.split())))
		if hex_mode else lambda d: d.encode("utf-8")
	)
	data = ""
	while not stop_event.is_set():
		await _sleep(0)
		# send serial data if given
		if data:
			try:
				await serial.write_async(formatter(data))
			except Exception as e:
				_stdout.write(f"error while sending: {e}\n")
		_stdout.write(">>> ")
		data = await input_async()
		_stdout.flush()

async def main():
	# register cmdline args parser
	parser = _ArgumentParser(description = "serial port communicator")
	parser.add_argument(
		"-l", "--list", action = "store_true",
		help = "list serial ports"
	)
	parser.add_argument(
		"-p", "--port", type = str,
		help = "specify a serial port (auto detected by default)"
	)
	parser.add_argument(
		"-b", "--baudrate", type=int, default = 9600,
		help='specify baudrate (default is 9600)'
	)
	parser.add_argument(
		"-x", "--hex", action = "store_true",
		help = "send and receive data in hexadecimal mode"
	)
	parser.add_argument(
		"-t", "--timeout", type = float, default = 0.1,
		help = "timeout for receiving data (default is 0.1)"
	)
	args = parser.parse_args()

	# list available ports
	if args.list:
		ports = list_ports()
		_stdout.write(
			f"list of serial ports: '{'\', \''.join(ports)}'\n"
			if ports else "no serial ports available\n"
		)
		_exit(0)

	# choose the port to connect to
	if args.port:
		port = args.port
	else:
		ports = list_ports()
		if not ports:
			_stdout.write("no serial ports available\n")
			_exit(1)
		port = next(iter(ports))

	# connect to the port
	try:
		serial = connect_port(port, args.baudrate)
	except Exception as e:
		_stdout.write(f"failed to connect to port '{port}': {e}\n")
		_exit(1)
	_stdout.write(f"""connected to '{port}'，baudrate {args.baudrate}{
		', hexadecimal mode' if args.hex else ''
	}\n""")

	# register stop event
	stop_event = _Event()
	def shutdown(*args, **kwargs):
		if not stop_event.set():
			stop_event.set()
	_register(shutdown)
	_signal(_SIGINT, shutdown)
	_signal(_SIGTERM, shutdown)

	# launch serial handlers
	await _gather(
		serial_read_handler(serial, stop_event, args.hex),
		serial_send_handler(serial, stop_event, args.hex)
	)
	# after shutdown
	serial.close()

if __name__ == '__main__':
	_run(main())
