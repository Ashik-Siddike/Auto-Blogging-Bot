-- Table: blog_sources
-- Stores the Twitter handles and their assigned niche/category
CREATE TABLE IF NOT EXISTS public.blog_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    twitter_handle TEXT NOT NULL UNIQUE,
    niche TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Table: blog_posts
-- Stores the generated articles to ensure we don't process the same tweet twice
CREATE TABLE IF NOT EXISTS public.blog_posts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID REFERENCES public.blog_sources(id),
    original_tweet_id TEXT NOT NULL UNIQUE, -- to prevent duplicate blogs for the same tweet
    original_tweet_url TEXT NOT NULL,
    title TEXT NOT NULL,
    content_html TEXT NOT NULL,
    seo_keywords TEXT,
    meta_description TEXT,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Optional: Insert a test source
-- INSERT INTO public.blog_sources (twitter_handle, niche) VALUES ('OpenAI', 'Artificial Intelligence');
