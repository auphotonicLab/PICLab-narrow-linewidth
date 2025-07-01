import pandas as pd
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def clean_body_text(text):
    """
    Cleans the body of text by removing URLs, safelinks, and content in angle brackets.
    """
    text = str(text)
    text = re.sub(r'http\S+', ' ', text)
    text = re.sub(r'\S*safelinks\.protection\.outlook\.com\S*', ' ', text)
    text = re.sub(r'<.*?>', ' ', text)
    return text

def extract_articles_nature(body):
    """
    Extracts article info from standard Nature eAlerts.
    Splits on double newlines (any line ending), expects:
    Title <\nAuthors\nDate\n<
    Returns a list of dicts: {title, authors, date, link}
    """
    articles = []
    # Split on two or more newlines (robust to \r, \n, \r\n)
    blocks = re.split(r'(?:\r?\n){2,}', str(body))
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        # Title line ends with <
        if lines[0].endswith('<'):
            title = lines[0][:-1].strip()
            authors = lines[1]
            date = lines[2]
            link = ''
            # Find the first line after date that ends with < (optional link)
            for l in lines[3:]:
                if l.endswith('<'):
                    link = l
                    break
            if re.match(r'^\d{1,2} \w+ \d{4}$', date) and authors and title and not any(x in title.lower() for x in ['view more articles', 'related subjects']):
                articles.append({
                    'title': title,
                    'authors': authors,
                    'date': date,
                    'link': link
                })
    return articles

def extract_articles_nature_special(body):
    """
    Extracts article info for npj Quantum Information and Light: Science & Application.
    Splits on double newlines (any line ending), expects:
    Title <\nAuthors\nType | Date | ... | ...\n<\n<
    Returns a list of dicts: {title, authors, date, link}
    """
    articles = []
    blocks = re.split(r'(?:\r?\n){2,}', str(body))
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        # Title line ends with <
        if lines[0].endswith('<'):
            title = lines[0][:-1].strip()
            authors = lines[1]
            type_date = lines[2]
            # Extract date from pipe-separated line
            date = ''
            for part in type_date.split('|'):
                part = part.strip()
                if re.match(r'^\d{1,2} \w+ \d{4}$', part):
                    date = part
                    break
            # Find the first line after type_date that ends with < (optional link)
            link = ''
            for l in lines[3:]:
                if l.endswith('<'):
                    link = l
                    break
            if date and authors and title and not any(x in title.lower() for x in ['view more articles', 'related subjects']):
                articles.append({
                    'title': title,
                    'authors': authors,
                    'date': date,
                    'link': link
                })
    return articles

def extract_articles_aps(body):
    """
    Extracts articles from APS journals (e.g., Physical Review Letters).
    Finds the 'LETTERS' section, then parses blocks:
    Title <\nAuthors\nPhys. Rev. Lett. ... – Published DATE\n< (optional)\n[abstract or blank]
    Returns a list of dicts: {title, authors, date, journal, link}
    """
    articles = []
    # Find the 'LETTERS' section
    text = str(body)
    m = re.search(r'LETTERS[\r\n]+(.+)', text, re.DOTALL | re.IGNORECASE)
    if not m:
        return articles
    section = m.group(1)
    # Split on double newlines (robust)
    blocks = re.split(r'(?:\r?\n){2,}', section)
    i = 0
    while i < len(blocks):
        lines = [l.strip() for l in blocks[i].splitlines() if l.strip()]
        # Skip theme and editor suggestion lines
        if not lines or any(x in lines[0].lower() for x in ["editors' suggestion", 'editor', 'theme', 'quantum information', 'science, and technology']):
            i += 1
            continue
        # Look for a title line ending with <
        if lines and lines[0].endswith('<'):
            title = lines[0][:-1].strip()
            # Next non-empty line(s) are authors
            authors = ''
            journal = ''
            date = ''
            link = ''
            # Find authors (first line after title that is not journal info)
            for j in range(1, len(lines)):
                if lines[j].startswith('Phys. Rev.'):
                    journal = lines[j]
                    # Extract date from journal line
                    mdate = re.search(r'Published (\d{1,2} \w+ \d{4})', journal)
                    if mdate:
                        date = mdate.group(1)
                elif lines[j].endswith('<'):
                    link = lines[j]
                elif not authors:
                    authors = lines[j]
            articles.append({
                'title': title,
                'authors': authors,
                'date': date,
                'journal': journal,
                'link': link
            })
        i += 1
    return articles

def extract_articles_arxiv(body):
    """
    Extracts articles from Physics daily/arXiv emails.
    Each article block starts with '\\' followed by 'arXiv:', then contains Date, Title, Authors.
    Returns a list of dicts: {arxiv_id, date, title, authors}
    """
    articles = []
    blocks = re.split(r'\\\s*\narXiv:', str(body))
    for block in blocks[1:]:
        lines = block.splitlines()
        arxiv_id = lines[0].strip() if lines else ''
        date = ''
        title = ''
        authors = ''
        for i, line in enumerate(lines):
            if line.startswith('Date:'):
                date = line.replace('Date:', '').strip()
            elif line.startswith('Title:'):
                title = line.replace('Title:', '').strip()
            elif line.startswith('Authors:'):
                authors = line.replace('Authors:', '').strip()
        articles.append({
            'arxiv_id': arxiv_id,
            'date': date,
            'title': title,
            'authors': authors
        })
    return articles

def extract_articles_optica(body):
    """
    Extracts articles from Optica journals.
    Looks for blocks: Title <, Authors, Journal info (e.g., 'Optica Quantum 2(5), ...').
    Returns a list of dicts: {title, authors, journal}
    """
    articles = []
    lines = [l.strip() for l in str(body).splitlines() if l.strip()]
    i = 0
    while i < len(lines) - 2:
        # Look for a title line ending with <
        if lines[i].endswith('<'):
            title = lines[i][:-1].strip()
            authors = lines[i+1]
            journal = ''
            # Find the first line after authors that looks like journal info
            for j in range(i+2, min(i+5, len(lines))):
                if re.match(r'.*\d+\(\d+\),.*\(\d{4}\)', lines[j]):
                    journal = lines[j]
                    break
            if title and authors and journal:
                articles.append({
                    'title': title,
                    'authors': authors,
                    'journal': journal
                })
            i += 3
        else:
            i += 1
    return articles

def journal_date_nature(subject):

    journal = subject[:-13]

    date = subject[-11:]

    return journal, date

def extract_articles_generic(body):
    """
    A generic fallback extractor for publishers without specific logic.
    Returns a list of dicts with at least 'title'.
    """
    lines = str(body).splitlines()
    articles = []
    for line in lines:
        line = line.strip()
        if 5 < len(line) < 200 and line and line[0].isupper():
            articles.append({'title': line, 'authors': '', 'date': '', 'link': ''})
    return articles

# --- Journal Extractor Registry ---

# Each entry: (matcher_function, extractor_function)
journal_extractors = []

def register_journal_extractor(matcher, extractor):
    journal_extractors.append((matcher, extractor))

# Matcher functions

def match_nature_special(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'npj quantum information' in s or 'light: science & applications' in s

def match_nature(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'nature portfolio ealerts' in s or 'nature' in s

def match_aps(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'physical review letters' in s or 'aps' in s

def match_arxiv(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'physics daily' in s or 'arxiv' in s

def match_optica(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'optica' in s

# Register known extractors
register_journal_extractor(match_nature_special, extract_articles_nature_special)
register_journal_extractor(match_nature, extract_articles_nature)
register_journal_extractor(match_aps, extract_articles_aps)
register_journal_extractor(match_arxiv, extract_articles_arxiv)
register_journal_extractor(match_optica, extract_articles_optica)

# --- Optics Communications (ScienceDirect) ---
def extract_articles_sciencedirect(body):
    """
    Extracts articles from Optics Communications (ScienceDirect) alerts.
    Looks for blocks: Title, Authors, Journal info, Date, Link.
    """
    articles = []
    blocks = re.split(r'(?:\r?\n){2,}', str(body))
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        # Heuristic: Title is first, authors second, journal info or date/link after
        title = lines[0]
        authors = lines[1] if len(lines) > 1 else ''
        date = ''
        link = ''
        for l in lines[2:]:
            if re.match(r'^\d{1,2} \w+ \d{4}$', l):
                date = l
            elif l.startswith('http') or l.endswith('<'):
                link = l
        if title and authors:
            articles.append({
                'source': 'Optics Communications',
                'date': date,
                'title': title,
                'authors': authors,
                'link': link,
                'raw': title
            })
    return articles

# --- IEEE Xplore Content Alert ---
def extract_articles_ieee(body):
    """
    Extracts articles from IEEE Xplore Content Alert.
    Looks for blocks: Title, Authors, Date, Link.
    """
    articles = []
    blocks = re.split(r'(?:\r?\n){2,}', str(body))
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        title = lines[0]
        authors = lines[1] if len(lines) > 1 else ''
        date = ''
        link = ''
        for l in lines[2:]:
            if re.match(r'^\d{1,2} \w+ \d{4}$', l):
                date = l
            elif l.startswith('http') or l.endswith('<'):
                link = l
        if title and authors:
            articles.append({
                'source': 'IEEE Xplore',
                'date': date,
                'title': title,
                'authors': authors,
                'link': link,
                'raw': title
            })
    return articles

# --- Optica Publishing Group (Optics Express, Optics Letters, Photonics Research, JOSA A/B, Applied Optics) ---
def extract_articles_optica_pg(body):
    """
    Extracts articles from Optica Publishing Group journals.
    Looks for blocks: Title <, Authors, Journal info (e.g., 'Optics Express ...').
    """
    articles = []
    lines = [l.strip() for l in str(body).splitlines() if l.strip()]
    i = 0
    while i < len(lines) - 2:
        if lines[i].endswith('<'):
            title = lines[i][:-1].strip()
            authors = lines[i+1]
            journal = ''
            for j in range(i+2, min(i+5, len(lines))):
                if re.search(r'(Optics|Photonics|JOSA|Applied Optics)', lines[j]):
                    journal = lines[j]
                    break
            if title and authors and journal:
                articles.append({
                    'source': journal,
                    'date': '',
                    'title': title,
                    'authors': authors,
                    'link': '',
                    'raw': title
                })
            i += 3
        else:
            i += 1
    return articles

# --- Improved APS Journals (Physical Review Letters) ---
def extract_articles_aps_new(body):
    """
    Extracts articles from APS Journals (Physical Review Letters, new format).
    Finds 'HIGHLIGHTED ARTICLES' or 'From the article', then parses blocks: Title <, Authors, Journal info (Phys. Rev. ...), Date.
    """
    articles = []
    # Find the section after 'HIGHLIGHTED ARTICLES' or 'From the article'
    m = re.search(r'(HIGHLIGHTED ARTICLES|From the article)(.+)', str(body), re.DOTALL | re.IGNORECASE)
    if not m:
        return articles
    section = m.group(2)
    blocks = re.split(r'(?:\r?\n){2,}', section)
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        if lines[0].endswith('<'):
            title = lines[0][:-1].strip()
            authors = lines[1]
            journal = ''
            date = ''
            for l in lines[2:]:
                if l.startswith('Phys. Rev.'):
                    journal = l
                    mdate = re.search(r'Published (\d{1,2} \w+ \d{4})', l)
                    if mdate:
                        date = mdate.group(1)
            articles.append({
                'source': journal or 'Physical Review Letters',
                'date': date,
                'title': title,
                'authors': authors,
                'link': '',
                'raw': title
            })
    return articles

# --- Update registry ---
def match_sciencedirect(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'sciencedirect' in s or 'optics communications' in s

def match_ieee(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'ieee xplore' in s

def match_optica_pg(sender, subject):
    s = (sender + ' ' + subject).lower()
    return any(j in s for j in ['optics express', 'optics letters', 'photonics research', 'josa a', 'josa b', 'applied optics'])

def match_aps_new(sender, subject):
    s = (sender + ' ' + subject).lower()
    return 'physical review letters' in s or 'aps journals' in s

# Insert these before the fallback in the registry
journal_extractors.insert(0, (match_sciencedirect, extract_articles_sciencedirect))
journal_extractors.insert(0, (match_ieee, extract_articles_ieee))
journal_extractors.insert(0, (match_optica_pg, extract_articles_optica_pg))
journal_extractors.insert(0, (match_aps_new, extract_articles_aps_new))

# --- Generic extractor that tries to guess article blocks ---
def extract_articles_generic_smart(body):
    """
    Attempts to extract articles from unknown journal formats.
    Looks for blocks of 2-4 lines: title, authors, (date), (link).
    Returns a list of dicts: {title, authors, date, link, raw}
    """
    articles = []
    blocks = re.split(r'(?:\r?\n){2,}', str(body))
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        title = lines[0]
        authors = lines[1] if len(lines) > 1 else ''
        date = ''
        link = ''
        # Try to find a date and link in the next lines
        for l in lines[2:]:
            if re.match(r'^\d{1,2} \w+ \d{4}$', l):
                date = l
            elif l.startswith('http') or l.endswith('<'):
                link = l
        articles.append({
            'title': title,
            'authors': authors,
            'date': date,
            'link': link,
            'raw': title
        })
    return articles

# Register as fallback
register_journal_extractor(lambda s, sub: True, extract_articles_generic_smart)

# --- Extractor selection ---
def get_article_extractor(sender_name, subject=None):
    for matcher, extractor in journal_extractors:
        if matcher(sender_name, subject or ''):
            print(f"INFO: Using extractor {extractor.__name__} for '{subject or sender_name}'")
            return extractor
    # fallback (should not happen)
    return extract_articles_generic_smart

# --- Configuration ---
INPUT_CSV_PATH = r"C:\Users\au617810\OneDrive - Aarhus universitet\Documents\new_articles.CSV"
OUTPUT_CSV_PATH = "top_articles.csv"

# --- Main Script ---

# Step 1: Load and clean the data
print(f"Loading data from {INPUT_CSV_PATH}...")
df = pd.read_csv(INPUT_CSV_PATH)
print("Cleaning email bodies...")
df['Body'] = df['Body'].apply(clean_body_text)

# Step 2: Define your interests
keywords = ["photonic", "quantum", "coherence", "laser", "feedback", "linewidth", "SG-DBR", "squeezed", "DBR", "DFB"]
interest_summary = "ultra-narrow linewidth lasers, SG-DBR laser, optical feedback, integrated photonics, coherence collapse"

# Step 3: Extract articles using publisher-specific logic
print("Extracting articles from email bodies...")
articles = []
for i, row in df.iterrows():
    body = row["Body"]
    subject = row["Subject"]
    sender = row.get("From: (Name)", "")
    extractor = get_article_extractor(sender, subject)
    extracted_articles = extractor(body)
    for art in extracted_articles:
        # Compose source field smartly
        source = (
            art.get("journal") or
            art.get("arxiv_id") or
            (subject[:-13] if 'nature' in extractor.__name__ and len(subject) > 13 else None) or
            sender or
            "Unknown Source"
        )
        articles.append({
            "source": source,
            "date": art.get("date") or row.get("ReceivedTime", row.get("Date", "")),
            "title": art.get("title", ""),
            "authors": art.get("authors", ""),
            "link": art.get("arxiv_id", "") or art.get("link", ""),
            "raw": art.get("raw", art.get("title", ""))
        })
    print(i,subject,sender,len(articles))

if not articles:
    print("\nWarning: No articles were extracted. Please check the extractor logic and your CSV content. Exiting.")
    exit()

print(f"\nExtracted {len(articles)} articles in total.")
articles_df = pd.DataFrame(articles)

# Step 4: Score the extracted articles
print("Scoring articles...")
def keyword_score(text):
    text_lower = text.lower()
    return sum(k in text_lower for k in keywords)

articles_df["keyword_hits"] = articles_df["title"].apply(keyword_score)

corpus = [interest_summary] + articles_df["title"].tolist()
vectorizer = TfidfVectorizer(stop_words='english')
X = vectorizer.fit_transform(corpus)
articles_df["tfidf_score"] = cosine_similarity(X[0:1], X[1:]).flatten()

articles_df["score"] = articles_df["keyword_hits"] + articles_df["tfidf_score"]

# Step 5: Output the top results
print(f"Saving top 20 articles to {OUTPUT_CSV_PATH}...")
top_articles = articles_df.sort_values("score", ascending=False).head(20)
top_articles[["date", "source", "title", "authors", "link", "score"]].to_csv(OUTPUT_CSV_PATH, index=False)

print("\n--- Top 20 Scored Articles ---")
print(top_articles[["title", "score"]])
print("\nScript finished successfully.")

# # --- Print example bodies for each unique sender/subject ---
# printed = set()
# print("\n--- EXAMPLES OF EMAIL BODIES BY JOURNAL ---")
# for i, row in df.iterrows():
#     sender = row.get("From: (Name)", "")
#     subject = row["Subject"]
#     key = (sender.strip(), subject.strip())
#     if key not in printed:
#         print(f"\n--- Example for sender: {sender} | subject: {subject} ---\n")
#         print(row["Body"][:2000])  # Print up to 2000 chars for brevity
#         printed.add(key)
#     if len(printed) >= 20:  # Limit to 10 examples for now
#         break
# # --- End of example printing ---

# # print(df["Body"][0],df["Body"][3])
