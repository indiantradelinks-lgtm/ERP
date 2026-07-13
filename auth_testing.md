# Auth Testing Playbook

Admin credentials: `admin@erp.com` / `Admin@123`

## Step 1: MongoDB
mongosh -> use erp_database -> db.users.find({role: "super_admin"}).pretty()
- Verify bcrypt hash starts with `$2b$`
- Indexes: users.email (unique), login_attempts.identifier, password_reset_tokens.expires_at (TTL)

## Step 2: API
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@erp.com","password":"Admin@123"}'
curl -b cookies.txt http://localhost:8001/api/auth/me
