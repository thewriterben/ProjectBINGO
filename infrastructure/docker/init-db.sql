-- PostgreSQL Initialization Script for ProjectBINGO
-- Creates all necessary tables and indexes

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'buyer',
    wallet_address VARCHAR(42),
    profile JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_role CHECK (role IN ('buyer', 'manufacturer', 'admin'))
);

-- Manufacturers table
CREATE TABLE IF NOT EXISTS manufacturers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    company_name VARCHAR(255) NOT NULL,
    capabilities TEXT[],
    certifications TEXT[],
    materials TEXT[],
    equipment TEXT[],
    capacity INTEGER,
    rating DECIMAL(3,2) DEFAULT 0.0,
    review_count INTEGER DEFAULT 0,
    location VARCHAR(255),
    portfolio JSONB DEFAULT '[]',
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES users(id) ON DELETE CASCADE,
    manufacturer_id UUID REFERENCES users(id) ON DELETE SET NULL,
    specifications TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    material VARCHAR(100),
    dimensions JSONB,
    deadline TIMESTAMP,
    price DECIMAL(10,2),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    estimated_completion TIMESTAMP,
    actual_completion TIMESTAMP,
    blockchain_tx_hash VARCHAR(66),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN (
        'pending', 'assigned', 'in_production', 
        'completed', 'cancelled', 'disputed'
    ))
);

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'ETH',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    blockchain_tx_hash VARCHAR(66),
    escrow_address VARCHAR(42),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_payment_status CHECK (status IN (
        'pending', 'escrowed', 'released', 'refunded', 'failed'
    ))
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Reviews table
CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    reviewer_id UUID REFERENCES users(id) ON DELETE CASCADE,
    reviewee_id UUID REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_rating CHECK (rating >= 1 AND rating <= 5)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_wallet ON users(wallet_address);
CREATE INDEX IF NOT EXISTS idx_manufacturers_user ON manufacturers(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client_id);
CREATE INDEX IF NOT EXISTS idx_orders_manufacturer ON orders(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_reviews_order ON reviews(order_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewee ON reviews(reviewee_id);

-- Insert sample data
INSERT INTO users (id, email, password_hash, role, wallet_address) VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin@projectbingo.com', '$2a$10$dummyhashedpassword', 'admin', '0x0000000000000000000000000000000000000001'),
    ('00000000-0000-0000-0000-000000000002', 'buyer@example.com', '$2a$10$dummyhashedpassword', 'buyer', '0x0000000000000000000000000000000000000002'),
    ('00000000-0000-0000-0000-000000000003', 'manufacturer@example.com', '$2a$10$dummyhashedpassword', 'manufacturer', '0x0000000000000000000000000000000000000003')
ON CONFLICT (email) DO NOTHING;

INSERT INTO manufacturers (user_id, company_name, capabilities, materials, capacity, rating, location) VALUES
    ('00000000-0000-0000-0000-000000000003', 'Precision Manufacturing Co.', 
     ARRAY['CNC Machining', 'Metal Fabrication'], 
     ARRAY['steel', 'aluminum', 'brass'], 
     10000, 4.8, 'Detroit, MI')
ON CONFLICT DO NOTHING;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_manufacturers_updated_at BEFORE UPDATE ON manufacturers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_payments_updated_at BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
