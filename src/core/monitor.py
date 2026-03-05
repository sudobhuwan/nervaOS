"""
NervaOS System Monitor - Hardware and process monitoring using psutil

This module provides real-time system statistics for:
- CPU usage
- RAM usage  
- Disk usage
- Battery status
- Top processes by resource usage
"""

import asyncio
from typing import Dict, Any, List, Optional
from functools import partial

import psutil


class SystemMonitor:
    """
    Async-friendly system monitor using psutil.
    
    All heavy operations are run in a thread executor to avoid
    blocking the main event loop.
    """
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop
    
    async def _run_in_executor(self, func, *args):
        """Run a blocking function in the thread pool"""
        return await self.loop.run_in_executor(None, partial(func, *args))
    
    # ─────────────────────────────────────────────────────────────
    # CPU Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_cpu_percent(self, interval: float = 0.1) -> float:
        """Get current CPU usage percentage"""
        return await self._run_in_executor(psutil.cpu_percent, interval)
    
    async def get_cpu_count(self) -> Dict[str, int]:
        """Get CPU core counts"""
        return {
            'physical': psutil.cpu_count(logical=False) or 0,
            'logical': psutil.cpu_count(logical=True) or 0
        }
    
    async def get_cpu_freq(self) -> Dict[str, float]:
        """Get CPU frequency in MHz"""
        freq = psutil.cpu_freq()
        if freq:
            return {
                'current': freq.current,
                'min': freq.min,
                'max': freq.max
            }
        return {'current': 0, 'min': 0, 'max': 0}
    
    # ─────────────────────────────────────────────────────────────
    # Memory Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_ram_usage(self) -> Dict[str, Any]:
        """Get RAM usage statistics"""
        mem = psutil.virtual_memory()
        return {
            'total_gb': round(mem.total / (1024**3), 2),
            'used_gb': round(mem.used / (1024**3), 2),
            'available_gb': round(mem.available / (1024**3), 2),
            'percent': mem.percent
        }
    
    async def get_swap_usage(self) -> Dict[str, Any]:
        """Get swap usage statistics"""
        swap = psutil.swap_memory()
        return {
            'total_gb': round(swap.total / (1024**3), 2),
            'used_gb': round(swap.used / (1024**3), 2),
            'percent': swap.percent
        }
    
    # ─────────────────────────────────────────────────────────────
    # Disk Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_disk_usage(self, path: str = '/') -> Dict[str, Any]:
        """Get disk usage for a specific path"""
        usage = psutil.disk_usage(path)
        return {
            'total_gb': round(usage.total / (1024**3), 2),
            'used_gb': round(usage.used / (1024**3), 2),
            'free_gb': round(usage.free / (1024**3), 2),
            'percent': usage.percent
        }
    
    async def get_all_disk_partitions(self) -> List[Dict[str, Any]]:
        """Get all mounted disk partitions with usage"""
        partitions = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    'device': part.device,
                    'mountpoint': part.mountpoint,
                    'fstype': part.fstype,
                    'total_gb': round(usage.total / (1024**3), 2),
                    'used_gb': round(usage.used / (1024**3), 2),
                    'percent': usage.percent
                })
            except PermissionError:
                continue
        return partitions
    
    # ─────────────────────────────────────────────────────────────
    # Battery Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_battery_status(self) -> Optional[Dict[str, Any]]:
        """Get battery status (None if no battery)"""
        battery = psutil.sensors_battery()
        if battery:
            return {
                'percent': battery.percent,
                'plugged_in': battery.power_plugged,
                'time_left_minutes': battery.secsleft // 60 if battery.secsleft > 0 else None
            }
        return None
    
    # ─────────────────────────────────────────────────────────────
    # Process Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_top_processes_by_memory(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top N processes by memory usage"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info']):
            try:
                info = proc.info
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'],
                    'memory_percent': round(info['memory_percent'], 2),
                    'memory_mb': round(info['memory_info'].rss / (1024**2), 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by memory usage descending
        processes.sort(key=lambda x: x['memory_percent'], reverse=True)
        return processes[:limit]
    
    async def get_top_processes_by_cpu(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top N processes by CPU usage"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                info = proc.info
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'],
                    'cpu_percent': round(info['cpu_percent'], 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by CPU usage descending
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        return processes[:limit]
    
    async def get_top_memory_process(self) -> str:
        """Get a string describing the top memory consumer"""
        procs = await self.get_top_processes_by_memory(1)
        if procs:
            p = procs[0]
            return f"{p['name']} (PID {p['pid']}) using {p['memory_mb']} MB"
        return "Unknown"
    
    async def get_top_cpu_process(self) -> str:
        """Get a string describing the top CPU consumer"""
        procs = await self.get_top_processes_by_cpu(1)
        if procs:
            p = procs[0]
            return f"{p['name']} (PID {p['pid']}) using {p['cpu_percent']}% CPU"
        return "Unknown"
    
    # ─────────────────────────────────────────────────────────────
    # Network Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_network_io(self) -> Dict[str, float]:
        """Get network I/O statistics"""
        net = psutil.net_io_counters()
        return {
            'bytes_sent_mb': round(net.bytes_sent / (1024**2), 2),
            'bytes_recv_mb': round(net.bytes_recv / (1024**2), 2),
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv
        }
    
    async def is_network_available(self) -> bool:
        """Check if network is available by looking at active connections"""
        try:
            connections = psutil.net_connections(kind='inet')
            return len(connections) > 0
        except psutil.AccessDenied:
            # Assume network is available if we can't check
            return True
    
    # ─────────────────────────────────────────────────────────────
    # Aggregate Methods
    # ─────────────────────────────────────────────────────────────
    
    async def get_all_stats(self) -> Dict[str, Any]:
        """Get a comprehensive snapshot of all system stats"""
        ram = await self.get_ram_usage()
        disk = await self.get_disk_usage('/')
        battery = await self.get_battery_status()
        
        return {
            'cpu_percent': await self.get_cpu_percent(),
            'ram_percent': ram['percent'],
            'ram_used_gb': ram['used_gb'],
            'ram_total_gb': ram['total_gb'],
            'disk_percent': disk['percent'],
            'disk_free_gb': disk['free_gb'],
            'battery_percent': battery['percent'] if battery else None,
            'battery_plugged': battery['plugged_in'] if battery else None,
            'network_available': await self.is_network_available()
        }
    
    async def get_context_summary(self) -> str:
        """
        Get a human-readable summary of system state for AI context.
        This is used to inform the AI about the current system status.
        """
        stats = await self.get_all_stats()
        top_mem = await self.get_top_processes_by_memory(3)
        
        lines = [
            f"System Status:",
            f"- CPU: {stats['cpu_percent']}%",
            f"- RAM: {stats['ram_used_gb']}/{stats['ram_total_gb']} GB ({stats['ram_percent']}%)",
            f"- Disk: {stats['disk_percent']}% used, {stats['disk_free_gb']} GB free",
        ]
        
        if stats['battery_percent'] is not None:
            plug = "plugged in" if stats['battery_plugged'] else "on battery"
            lines.append(f"- Battery: {stats['battery_percent']}% ({plug})")
        
        if top_mem:
            lines.append("- Top memory consumers:")
            for p in top_mem:
                lines.append(f"  • {p['name']}: {p['memory_mb']} MB")
        
        return "\n".join(lines)
