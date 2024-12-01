# routes.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from .models import Service, ServiceUpdate, UserCreate, Token
from .auth import get_current_user, create_access_token, get_password_hash, verify_password
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from .database import get_db
from .monitor import check_ping, check_http, send_alert
from datetime import datetime, timedelta
import json
from email.mime.text import MIMEText
import smtplib
import ssl
from .models import SMTPConfig, Service, ServiceUpdate, UserCreate, Token



router = APIRouter()

@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", 
            (form_data.username,)
        ).fetchone()
        
        if not user or not verify_password(form_data.password, user[1]):
            raise HTTPException(
                status_code=400,
                detail="Incorrect username or password"
            )
            
    access_token = create_access_token(data={"sub": user[0]})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/users")
async def create_user(user: UserCreate):
    with get_db() as conn:
        hashed_password = get_password_hash(user.password)
        try:
            conn.execute(
                "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
                (user.username, hashed_password)
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Username already registered")
    return {"message": "User created successfully"}


@router.get("/services/")
async def get_services():
    with get_db() as conn:
        c = conn.cursor()
        services = c.execute('SELECT * FROM services').fetchall()
        services_list = []
        
        for service in services:
            latest_check = c.execute('''
                SELECT status, timestamp, response_time 
                FROM checks 
                WHERE service_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (service[0],)).fetchone()
            
            services_list.append({
                "id": service[0],
                "name": service[1],
                "type": service[2],
                "target": service[3],
                "check_frequency": service[4],
                "retry_threshold": service[5],
                "grace_period": service[6],
                "alert_email": service[7],
                "status": latest_check[0] if latest_check else "unknown",
                "last_check": latest_check[1] if latest_check else None,
                "response_time": latest_check[2] if latest_check else None
            })
            
    return {"services": services_list}


@router.post("/services")
async def add_service(
    service: Service
):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO services 
            (name, type, target, check_frequency, retry_threshold, grace_period, alert_email)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            service.name, service.type, service.target, service.check_frequency,
            service.retry_threshold, service.grace_period, service.alert_email
        ))
    return {"message": "Service added successfully"}

@router.put("/services/{service_id}")
async def update_service(
    service_id: int,
    service: Service,
    current_user: str = Depends(get_current_user)
):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE services 
            SET name=?, type=?, target=?, check_frequency=?, 
                retry_threshold=?, grace_period=?, alert_email=?
            WHERE id=?
        ''', (
            service.name, service.type, service.target, service.check_frequency,
            service.retry_threshold, service.grace_period, service.alert_email,
            service_id
        ))
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service not found")
    return {"message": "Service updated successfully"}

@router.delete("/services/{service_id}")
async def delete_service(
    service_id: int
):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM services WHERE id=?", (service_id,))
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service not found")
    return {"message": "Service deleted successfully"}


@router.get("/service_metrics/{service_id}/{time_range}")
async def get_service_metrics(service_id: int, time_range: str):
   with get_db() as conn:
       c = conn.cursor()
       now = datetime.now()
       
       if time_range == 'hour':
           start_time = now - timedelta(hours=1)
       elif time_range == 'day': 
           start_time = now - timedelta(days=1)
       else:
           start_time = now - timedelta(weeks=1)

       checks = c.execute('''
           SELECT timestamp, status, response_time
           FROM checks 
           WHERE service_id = ? AND timestamp >= ?
           ORDER BY timestamp ASC
       ''', (service_id, start_time.isoformat())).fetchall()

       timestamps = []
       response_times = []
       status_values = []
       outage_count = 0
       total_response_time = 0
       up_count = 0

       for check in checks:
           timestamps.append(datetime.fromisoformat(check[0]).strftime('%H:%M'))
           response_times.append(check[2] if check[2] else 0)
           status_value = 1 if check[1] == 'up' else 0
           status_values.append(status_value)
           
           if check[2]:
               total_response_time += check[2]
           if status_value == 1:
               up_count += 1
           else:
               outage_count += 1

       metrics = {
           'avg_response_time': total_response_time / len(checks) if checks else 0,
           'uptime': (up_count / len(checks) * 100) if checks else 0,
           'outage_count': outage_count
       }

       return {
           'timestamps': timestamps,
           'response_times': response_times,
           'status_values': status_values,
           'metrics': metrics
       }
   

@router.post("/services/{service_id}/test")
async def test_existing_service(service_id: int):
    with get_db() as conn:
        service = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        if service[2] == 'ping':
            status, response_time = await check_ping(service[3])
            details = {'method': 'ping'}
        else:
            status, response_time, details = await check_http(service[3])
        
        # Record check
        current_time = datetime.now().isoformat()
        try:
            conn.execute('''
                INSERT INTO checks 
                (service_id, timestamp, status, response_time, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                service_id,
                current_time,
                'up' if status else 'down',
                response_time,
                json.dumps(details)
            ))

            # If service is down, try to send alert
            if not status:
                await send_alert(service[7], service[1], 'down')
                
            return {
                "status": "up" if status else "down",
                "response_time": response_time,
                "details": details,
                "alert_sent": not status,
                "timestamp": current_time
            }
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                raise HTTPException(status_code=503, detail="Database is busy, please try again")
            raise



@router.get("/status_with_history")
async def get_status_with_history():
    with get_db() as conn:
        c = conn.cursor()
        services = c.execute('SELECT * FROM services').fetchall()
        status_data = []
        
        for service in services:
            service_id = service[0]
            latest_check = c.execute('''
                SELECT status, timestamp, response_time 
                FROM checks 
                WHERE service_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (service_id,)).fetchone()
            
            check_history = c.execute('''
                SELECT status 
                FROM checks 
                WHERE service_id = ?
                ORDER BY timestamp DESC 
                LIMIT 100
            ''', (service_id,)).fetchall()
            
            status_data.append({
                "id": service_id,
                "name": service[1],
                "type": service[2],
                "status": latest_check[0] if latest_check else "unknown",
                "last_check": latest_check[1] if latest_check else None,
                "response_time": latest_check[2] if latest_check else None,
                "check_history": [check[0] for check in check_history]
            })
        
    return {"services": status_data}


#current_user: str = Depends(get_current_user)
@router.get("/smtp")
async def get_smtp_config():
    with get_db() as conn:
        config = conn.execute("SELECT host, port, username, from_email, use_tls FROM smtp_config").fetchone()
        return {
            "host": config[0] if config else "",
            "port": config[1] if config else 587,
            "username": config[2] if config else "",
            "from_email": config[3] if config else "",
            "use_tls": config[4] if config else True
        }

@router.post("/smtp")
async def update_smtp_config(config: SMTPConfig):
    with get_db() as conn:
        conn.execute("DELETE FROM smtp_config")
        conn.execute('''
            INSERT INTO smtp_config (host, port, username, password, from_email, use_tls)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (config.host, config.port, config.username, config.password, 
              config.from_email, config.use_tls))
    return {"message": "SMTP configuration updated"}


#current_user: str = Depends(get_current_user)
@router.post("/smtp")
async def update_smtp_config(config: SMTPConfig, current_user: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM smtp_config")
        conn.execute('''
            INSERT INTO smtp_config (host, port, username, password, from_email, use_tls)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            config.host.strip(),
            config.port,
            config.username.strip(),
            config.password.strip(),
            config.from_email.strip(),
            config.use_tls
        ))
    return {"message": "SMTP configuration updated"}

@router.post("/smtp/test")
async def test_smtp():
    with get_db() as conn:
        config = conn.execute(
            "SELECT host, port, username, password, from_email, use_tls FROM smtp_config"
        ).fetchone()
        
    if not config:
        raise HTTPException(status_code=400, detail="SMTP not configured")
    
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
            
            msg = MIMEText("Test email", 'plain', 'utf-8')
            msg['Subject'] = 'Test Alert'
            msg['From'] = from_email
            msg['To'] = from_email
            
            server.send_message(msg)
        return {"message": "Test email sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error sending email: {str(e)}")