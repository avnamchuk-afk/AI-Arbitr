import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, ChevronRight, Clock3, ExternalLink, Search } from "lucide-react";
import { getKnowledgeArticle, knowledgeArticles, knowledgeCategories } from "./knowledgeContent.js";
import "./knowledge.css";

const articleHref = (slug) => `/knowledge/${slug}`;

function setPageMetadata(title, description) {
  document.title = title;
  let meta = document.querySelector('meta[name="description"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "description");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", description);
}

function KnowledgeHeader() {
  return (
    <header className="knowledge-header">
      <a className="knowledge-brand" href="/landing" aria-label="Вернуться на лендинг AI-Arbitr">
        <span>A</span><strong>AI-Arbitr</strong><i>beta</i>
      </a>
      <nav aria-label="Навигация базы знаний">
        <a href="/landing">О сервисе</a>
        <a href="/knowledge">База знаний</a>
      </nav>
      <a className="knowledge-start" href="/">Открыть сервис</a>
    </header>
  );
}

function RelatedArticles({ slugs }) {
  const articles = slugs.map(getKnowledgeArticle).filter(Boolean);
  return (
    <section className="knowledge-related">
      <h2>Читайте также</h2>
      <div>
        {articles.map((article) => (
          <a href={articleHref(article.slug)} key={article.slug}>
            <span>{article.category}</span>
            <strong>{article.title}</strong>
            <ChevronRight size={18} />
          </a>
        ))}
      </div>
    </section>
  );
}

function KnowledgeArticle({ article }) {
  useEffect(() => {
    setPageMetadata(`${article.title} | База знаний AI-Arbitr`, article.summary);
    window.scrollTo(0, 0);
  }, [article]);

  return (
    <main className="knowledge-page">
      <KnowledgeHeader />
      <div className="knowledge-article-layout">
        <aside className="knowledge-toc" aria-label="Оглавление статьи">
          <a href="/knowledge"><ArrowLeft size={16} /> Все статьи</a>
          <strong>В этой статье</strong>
          {article.sections.map((section, index) => (
            <a href={`#section-${index}`} key={section.title}>{section.title}</a>
          ))}
        </aside>
        <article className="knowledge-article">
          <header>
            <span className="knowledge-category">{article.category}</span>
            <h1>{article.title}</h1>
            <p>{article.summary}</p>
            <div className="knowledge-meta">
              <span><Clock3 size={15} /> {article.readingTime}</span>
              <span>Обновлено {article.updated}</span>
            </div>
          </header>
          {article.sections.map((section, index) => (
            <section id={`section-${index}`} key={section.title}>
              <h2>{section.title}</h2>
              {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
              {section.bullets && <ul>{section.bullets.map((item) => <li key={item}>{item}</li>)}</ul>}
            </section>
          ))}
          {article.sources?.length > 0 && (
            <section className="knowledge-sources">
              <h2>Правовые источники</h2>
              {article.sources.map(([label, href]) => (
                <a href={href} target="_blank" rel="noreferrer" key={href}>{label}<ExternalLink size={15} /></a>
              ))}
            </section>
          )}
          <div className="knowledge-disclaimer">
            Материал носит информационный характер и описывает текущую MVP-версию сервиса. Он не заменяет индивидуальную юридическую консультацию.
          </div>
          <a className="knowledge-primary" href="/">Попробовать в AI-Arbitr <ArrowRight size={18} /></a>
          <RelatedArticles slugs={article.related || []} />
        </article>
      </div>
    </main>
  );
}

function KnowledgeCatalog() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Все");
  const filteredArticles = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return knowledgeArticles.filter((article) => {
      const categoryMatches = category === "Все" || article.category === category;
      const queryMatches = !normalizedQuery || `${article.title} ${article.summary} ${article.category}`.toLowerCase().includes(normalizedQuery);
      return categoryMatches && queryMatches;
    });
  }, [category, query]);

  useEffect(() => {
    setPageMetadata(
      "База знаний AI-Arbitr",
      "Ответы о договорах, электронной подписи и досудебном разрешении споров в AI-Arbitr."
    );
  }, []);

  return (
    <main className="knowledge-page">
      <KnowledgeHeader />
      <section className="knowledge-hero">
        <BookOpen size={30} />
        <span>База знаний</span>
        <h1>Договоры без непонятных слов</h1>
        <p>Как составить, согласовать и подписать договор, а затем разрешить спор в соответствии с его условиями.</p>
        <label className="knowledge-search">
          <Search size={19} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти ответ" />
        </label>
      </section>
      <section className="knowledge-catalog">
        <div className="knowledge-filters" aria-label="Категории статей">
          {knowledgeCategories.map((item) => (
            <button className={item === category ? "active" : ""} onClick={() => setCategory(item)} key={item}>{item}</button>
          ))}
        </div>
        <p className="knowledge-count">Материалов: {filteredArticles.length}</p>
        <div className="knowledge-grid">
          {filteredArticles.map((article) => (
            <a className="knowledge-card" href={articleHref(article.slug)} key={article.slug}>
              <span>{article.category}</span>
              <h2>{article.title}</h2>
              <p>{article.summary}</p>
              <small>{article.readingTime}<ChevronRight size={16} /></small>
            </a>
          ))}
        </div>
        {filteredArticles.length === 0 && <div className="knowledge-empty">По этому запросу пока нет статьи.</div>}
      </section>
    </main>
  );
}

export default function KnowledgeBase() {
  const slug = window.location.pathname.match(/^\/knowledge\/([^/]+)\/?$/)?.[1];
  const article = slug ? getKnowledgeArticle(slug) : null;
  if (slug && !article) {
    return (
      <main className="knowledge-page">
        <KnowledgeHeader />
        <section className="knowledge-not-found"><h1>Статья не найдена</h1><a href="/knowledge">Вернуться в базу знаний</a></section>
      </main>
    );
  }
  return article ? <KnowledgeArticle article={article} /> : <KnowledgeCatalog />;
}
