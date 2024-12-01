from datetime import datetime
import asyncio
import aiohttp
import ping3
import json
from .database import get_db
from typing import Tuple, Dict, Union, Optional
from email.utils import formatdate
from email.mime.text import MIMEText
import smtplib
import ssl



async def check_ping(target: str) -> Tuple[bool, Optional[float]]:
    try:
        response_time = ping3.ping(target)
        return (True, response_time) if response_time is not None else (False, None)
    except Exception:
        return False, None

async def check_http(target: str) -> Tuple[bool, Optional[float], Dict]:
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            start_time = datetime.now()
            async with session.get(target, allow_redirects=True, 
                                 ssl=False,
                                 headers={'User-Agent': 'ServiceMonitor/1.0'}) as response:
                response_time = (datetime.now() - start_time).total_seconds()
                
                details = {
                    'status_code': response.status,
                    'redirect_count': len(response.history),
                    'final_url': str(response.url),
                    'response_time': response_time
                }
                
                return 200 <= response.status < 400, response_time, details
    except Exception as e:
        return False, None, {'error': str(e)}



async def send_alert(email: str, service_name: str, status: str):
    with get_db() as conn:
        config = conn.execute(
            "SELECT host, port, username, password, from_email, use_tls FROM smtp_config"
        ).fetchone()
        
    if not config:
        print("Alert not sent: SMTP not configured")
        return
        
    host = config[0].strip().encode('ascii', 'ignore').decode()
    port = config[1]
    username = config[2].strip().encode('ascii', 'ignore').decode()
    password = config[3].strip().encode('ascii', 'ignore').decode()
    from_email = config[4].strip().encode('ascii', 'ignore').decode()
    use_tls = config[5]
    
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            
            subject = f"Service Alert: {service_name} is {status.upper()}"
            body = f"""
Service: {service_name}
Status: {status.upper()}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            msg = MIMEText(body, 'plain', 'utf-8')
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = email
            msg['Date'] = formatdate(localtime=True)
            
            server.send_message(msg)
            print(f"Alert sent to {email}: {service_name} is {status}")
    except Exception as e:
        print(f"Failed to send alert: {str(e)}")
        with get_db() as conn:
            conn.execute(
                'INSERT INTO errors (timestamp, error) VALUES (?, ?)',
                (datetime.now().isoformat(), f"SMTP Error: {str(e)}")
            )




async def monitor_service(service: tuple):
    service_id, name, type_, target, freq, threshold, grace, email = service
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            # Get last alert
            last_alert = c.execute('''
                SELECT timestamp FROM alerts 
                WHERE service_id = ? 
                ORDER BY timestamp DESC LIMIT 1
            ''', (service_id,)).fetchone()
            
            # Perform check
            if type_ == 'ping':
                status, response_time = await check_ping(target)
                details = {'method': 'ping'}
            else:
                status, response_time, details = await check_http(target)
            
            current_time = datetime.now()
            
            # Record check
            c.execute('''
                INSERT INTO checks 
                (service_id, timestamp, status, response_time, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                service_id,
                current_time.isoformat(),
                'up' if status else 'down',
                response_time,
                json.dumps(details)
            ))
            
            # Handle alerts
            if not status:
                grace_period_start = current_time.timestamp() - (grace * 60)
                recent_checks = c.execute('''
                    SELECT status 
                    FROM checks 
                    WHERE service_id = ? 
                    AND datetime(timestamp) > datetime(?)
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (
                    service_id,
                    datetime.fromtimestamp(grace_period_start).isoformat(),
                    threshold
                )).fetchall()
                
                if (len(recent_checks) >= threshold and 
                    all(check[0] == 'down' for check in recent_checks)):
                    
                    should_alert = True
                    if last_alert:
                        last_alert_time = datetime.fromisoformat(last_alert[0])
                        time_since_last_alert = (current_time - last_alert_time).total_seconds()
                        should_alert = time_since_last_alert >= (grace * 60)
                    
                    if should_alert:
                        await send_alert(email, name, 'down')
                        c.execute('''
                            INSERT INTO alerts 
                            (service_id, timestamp, type, details)
                            VALUES (?, ?, ?, ?)
                        ''', (
                            service_id,
                            current_time.isoformat(),
                            'down',
                            json.dumps({
                                'status': 'down',
                                'details': details,
                                'response_time': response_time
                            })
                        ))
            
            elif status:
                last_check = c.execute('''
                    SELECT status 
                    FROM checks 
                    WHERE service_id = ? 
                    AND timestamp < ? 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                ''', (service_id, current_time.isoformat())).fetchone()
                
                if last_check and last_check[0] == 'down':
                    await send_alert(email, name, 'up')
                    c.execute('''
                        INSERT INTO alerts 
                        (service_id, timestamp, type, details)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        service_id,
                        current_time.isoformat(),
                        'recovery',
                        json.dumps({
                            'status': 'up',
                            'details': details,
                            'response_time': response_time
                        })
                    ))
            
    except Exception as e:
        with get_db() as conn:
            conn.execute('''
                INSERT INTO errors (timestamp, error)
                VALUES (?, ?)
            ''', (datetime.now().isoformat(), str(e)))

async def monitor_services():
    while True:
        try:
            with get_db() as conn:
                services = conn.execute('SELECT * FROM services').fetchall()
                
            tasks = [monitor_service(service) for service in services]
            await asyncio.gather(*tasks)
            
        except Exception as e:
            with get_db() as conn:
                conn.execute('''
                    INSERT INTO errors (timestamp, error)
                    VALUES (?, ?)
                ''', (datetime.now().isoformat(), str(e)))
        
        await asyncio.sleep(60)

async def start_monitoring():
    asyncio.create_task(monitor_services())