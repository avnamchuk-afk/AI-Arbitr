import React, { useEffect } from "react";
import {
  ArrowRight,
  BarChart3,
  Check,
  Clock3,
  Database,
  FileSignature,
  Globe2,
  LockKeyhole,
  Scale,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Users,
} from "lucide-react";
import "./landing.css";

const appHref = "/";

const howToSteps = [
  "Опишите условия договора в чате с AI.",
  "AI уточнит детали и подготовит проект.",
  "Проверьте карточку ключевых условий и текст договора.",
  "Отправьте ссылку второй стороне на email.",
  "После подписания второй стороной подпишите договор в своем чате.",
  "Получите PDF с отметками простой электронной подписи.",
];

const metrics = [
  ["0 ₽", "для физлиц, самозанятых, ИП и МСП"],
  ["5 минут", "среднее время составления договора"],
  ["1 минута", "ориентир для досудебного разбора спора"],
  ["iOS / Android", "работает в браузере, с VPN или без"],
];

const audiences = [
  "Физлица: найм жилья, аренда, услуги.",
  "Самозанятые и фрилансеры: подряд, разработка, услуги.",
  "ИП и МСП: договоры с клиентами и поставщиками.",
  "Инвесторы: снижение транзакционных издержек сделки.",
  "Крупный бизнес: корпоративные тарифы и аналитика.",
];

const trustItems = [
  "RAG-подход: ответы опираются на проверенные источники, а не на догадки.",
  "Шаблоны и процессы верифицированы юридической методологией.",
  "Простая электронная подпись работает по ФЗ №63.",
  "Персональные данные обрабатываются по принципу минимизации.",
  "Серверы и хранение данных ориентированы на требования РФ.",
  "Базовый сценарий бесплатен для физлиц, самозанятых, ИП и МСП.",
];

const team = [
  ["Alex", "Architecture & Legal Methodology"],
  ["Артур", "Legal Counsel"],
  ["Лена", "Finance & Unit Economics"],
  ["Ника", "Lead IT & AI Development"],
  ["Николай", "Growth & Marketing"],
  ["София", "Behavioral Psychology"],
];

const roadmap = [
  ["Октябрь 2026", "Безопасность, надежность и доступность"],
  ["Январь 2027", "Расширение перечня нейросетей"],
  ["Март 2027", "Многосторонние договоры"],
  ["Май 2027", "Регулярная публикация аналитики"],
  ["Июль 2027", "Алгоритмы перекрестной проверки генерации"],
  ["Сентябрь 2027", "Улучшение CJM и мобильного UX"],
  ["Декабрь 2027", "Пакеты корпоративных документов"],
  ["Февраль 2028", "Интеграции с ЭДО и бухгалтерией"],
  ["Май 2028", "Расширение способов разрешения споров"],
  ["Сентябрь 2028", "Рейтинги надежности контрагентов"],
  ["Октябрь 2028", "ЕАЭС/СНГ и трансграничные договоры"],
  ["Апрель 2029", "Платежная экосистема и эскроу"],
  ["Октябрь 2029", "Микро-страхование рисков неплатежей"],
  ["Январь 2030", "Сеть доверенных юристов-партнеров для регрессного взыскания"],
];

const futureCycle = [
  "Проверка контрагента",
  "Заключение договора",
  "Эскроу и страхование",
  "Исполнение или разрешение спора",
  "Страховая выплата",
  "Регрессное взыскание",
  "Обновление рейтинга",
];

const faq = [
  ["Что такое AI-Arbitr?", "AI-Arbitr — платформа для заключения договоров и разрешения споров с помощью искусственного интеллекта без участия юристов и судов."],
  ["AI-Arbitr действительно бесплатный?", "Да. Для физлиц, самозанятых, ИП и МСП базовый сценарий бесплатен навсегда."],
  ["Имеют ли договоры юридическую силу?", "Да. Договор подписывается простой электронной подписью, а финальный PDF фиксирует действия сторон."],
  ["Может ли нейросеть ошибиться?", "Риск снижается за счет шаблонов, юридической методологии и проверки пользователем перед согласованием."],
  ["Как разрешаются споры?", "Сторона открывает спор, сервис анализирует условия договора и историю согласования для досудебного урегулирования."],
  ["Можно ли обратиться в суд?", "Да. AI-Arbitr не заменяет суд, а помогает собрать договор, историю и справку для доказательной базы."],
  ["На каких устройствах работает сервис?", "На iPhone и Android в браузере. Устанавливать приложение не нужно."],
  ["Как защищаются данные?", "Мы минимизируем хранение персональных данных и не сохраняем полный пакет идентифицирующих данных после финализации."],
  ["Какие договоры доступны?", "MVP особенно хорошо отрабатывает найм жилого помещения, остальные типовые договоры генерируются по упрощенному сценарию."],
  ["Почему нет приложения в App Store?", "Веб-сервис не зависит от App Store и Google Play, работает с VPN или без него."],
  ["Что если вторая сторона не подпишет?", "Договор не вступает в силу, а черновик остается в архиве."],
  ["Можно ли забрать данные?", "Да. Данные и документы должны оставаться под контролем пользователя."],
];

function LandingSchema() {
  const schema = [
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: faq.map(([question, answer]) => ({
        "@type": "Question",
        name: question,
        acceptedAnswer: { "@type": "Answer", text: answer },
      })),
    },
    {
      "@context": "https://schema.org",
      "@type": "HowTo",
      name: "Как заключить договор через AI-Arbitr",
      step: howToSteps.map((text) => ({ "@type": "HowToStep", text })),
    },
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "AI-Arbitr",
      url: "https://ai-arbitr.ru",
      founder: "Alex",
      employee: team.map(([name]) => name),
    },
  ];
  return <script type="application/ld+json">{JSON.stringify(schema)}</script>;
}

function LandingHeader() {
  return (
    <header className="landing-header">
      <a className="landing-brand" href="#top" aria-label="AI-Arbitr">
        <span>A</span>
        <strong>AI-Arbitr</strong>
        <i>beta</i>
      </a>
      <nav aria-label="Навигация лендинга">
        <a href="#how">Как работает</a>
        <a href="#trust">Доверие</a>
        <a href="#faq">FAQ</a>
      </nav>
      <a className="landing-header-cta" href={appHref}>Начать</a>
    </header>
  );
}

function Section({ eyebrow, title, children, className = "" }) {
  return (
    <section className={`landing-section ${className}`}>
      {eyebrow && <span className="landing-eyebrow">{eyebrow}</span>}
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export default function LandingPage() {
  useEffect(() => {
    document.title = "AI-Arbitr — договоры и споры без юристов и судов | Бесплатно навсегда";
    const description = "Первая в России платформа для заключения договоров и разрешения споров с помощью ИИ. Бесплатно для физлиц, самозанятых, ИП и МСП.";
    let meta = document.querySelector('meta[name="description"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "description");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", description);
  }, []);

  return (
    <main className="landing-page" id="top">
      <LandingSchema />
      <LandingHeader />

      <section className="landing-hero">
        <div className="landing-hero-copy">
          <span className="landing-eyebrow">Первые в России</span>
          <h1>Без юристов. Без судов. Без формализма и бюрократии.</h1>
          <p>
            AI-Arbitr помогает составить договор, согласовать его со второй стороной,
            подписать простой электронной подписью и открыть спор, если он возникнет.
          </p>
          <div className="landing-cta-row">
            <a className="landing-primary" href={appHref}>Начать бесплатно <ArrowRight size={18} /></a>
            <a className="landing-secondary" href="#how">Как это работает</a>
          </div>
          <small>iPhone или Android | С VPN или без | Без ввода карты | Попробуйте без регистрации</small>
        </div>
        <div className="landing-visual" aria-label="Клиентский путь AI-Arbitr">
          <div className="visual-card main">
            <Scale size={28} />
            <strong>Составить</strong>
            <span>договор за 5 минут</span>
          </div>
          <div className="visual-card">
            <FileSignature size={24} />
            <strong>Подписать</strong>
            <span>ПЭП + PDF</span>
          </div>
          <div className="visual-card">
            <ShieldCheck size={24} />
            <strong>Разрешить спор</strong>
            <span>досудебно</span>
          </div>
        </div>
      </section>

      <Section eyebrow="Определение" title="Что такое AI-Arbitr?">
        <p className="landing-lead">
          AI-Arbitr — платформа для заключения договоров и разрешения споров с помощью искусственного интеллекта.
          Сервис создан для физлиц, самозанятых, ИП и МСП, которым нужен понятный договор без дорогой юридической бюрократии.
        </p>
        <div className="landing-note">
          По рыночной логике LegalTech люди ищут быстрые и доступные альтернативы разовым юридическим услугам.
          AI-Arbitr закрывает этот разрыв через мобильный чат, карточку условий и юридически значимый PDF.
        </div>
      </Section>

      <Section eyebrow="Сравнение" title="AI-Arbitr vs традиционные юристы">
        <div className="landing-table-wrap">
          <table className="landing-table">
            <thead>
              <tr><th>Параметр</th><th>Традиционный путь</th><th>AI-Arbitr</th></tr>
            </thead>
            <tbody>
              <tr><td>Стоимость</td><td>7 000-50 000 ₽</td><td>Бесплатно для физлиц, самозанятых, ИП и МСП</td></tr>
              <tr><td>Время</td><td>3-10 дней</td><td>Около 5 минут</td></tr>
              <tr><td>Спор</td><td>Суд и месяцы ожидания</td><td>Досудебный сценарий в чате</td></tr>
              <tr><td>Доступность</td><td>По записи</td><td>24/7 со смартфона</td></tr>
            </tbody>
          </table>
        </div>
      </Section>

      <Section eyebrow="Путь пользователя" title="Как заключить договор через AI-Arbitr?" className="landing-split" >
        <ol className="landing-steps" id="how">
          {howToSteps.map((step, index) => <li key={step}><span>{index + 1}</span>{step}</li>)}
        </ol>
      </Section>

      <Section eyebrow="Метрики" title="AI-Arbitr в цифрах">
        <div className="landing-metrics">
          {metrics.map(([value, label]) => (
            <article key={value}>
              <strong>{value}</strong>
              <span>{label}</span>
            </article>
          ))}
        </div>
      </Section>

      <Section eyebrow="Технологии" title="Почему современный ИИ больше не должен гадать в документах">
        <div className="landing-cards three">
          <article><Database /><strong>RAG</strong><p>Модель опирается на проверяемые источники и шаблоны, а не на свободные домыслы.</p></article>
          <article><Sparkles /><strong>Юридическая методология</strong><p>Ключевые формулировки фиксируются и тестируются на типовых сценариях.</p></article>
          <article><BarChart3 /><strong>Аналитика</strong><p>Сервис собирает обезличенные события и помогает улучшать договорные практики.</p></article>
        </div>
      </Section>

      <Section eyebrow="Доступ" title="Веб-сервис, а не приложение из стора">
        <div className="landing-cards">
          <article><Globe2 /><strong>Без App Store и Google Play</strong><p>Откройте браузер и работайте. Ничего не нужно устанавливать.</p></article>
          <article><Smartphone /><strong>Mobile-first</strong><p>Основной сценарий оптимизирован под смартфон и быстрые действия.</p></article>
          <article><LockKeyhole /><strong>VPN или без</strong><p>Веб-доступ меньше зависит от ограничений магазинов приложений.</p></article>
        </div>
      </Section>

      <Section eyebrow="Ценность" title="Зачем использовать AI-Arbitr?">
        <div className="landing-problems">
          <article><strong>Юристы стоят дорого</strong><p>Базовый сценарий бесплатен для физлиц, самозанятых, ИП и МСП.</p></article>
          <article><strong>Договор кажется сложным</strong><p>Чат переводит юридическую логику в понятные шаги и карточку условий.</p></article>
          <article><strong>Суд занимает месяцы</strong><p>Спор сначала разбирается в досудебном цифровом сценарии.</p></article>
        </div>
      </Section>

      <Section eyebrow="Аудитории" title="Для кого создан AI-Arbitr?">
        <div className="landing-audience">
          {audiences.map((item) => <p key={item}><Check size={16} />{item}</p>)}
        </div>
      </Section>

      <Section eyebrow="Сценарии" title="Когда использовать AI-Arbitr?">
        <div className="landing-cards">
          <article><Clock3 /><strong>Когда нужно быстро</strong><p>Договор нужен сегодня, а не после недели согласований.</p></article>
          <article><Scale /><strong>Когда важна сила документа</strong><p>PDF фиксирует текст, стороны и действия в сервисе.</p></article>
          <article><ShieldCheck /><strong>Когда нужен баланс</strong><p>Методология ориентирована на добросовестность сторон.</p></article>
        </div>
      </Section>

      <Section eyebrow="Доверие" title="Почему можно доверять?" className="landing-trust" >
        <div id="trust" className="landing-checks">
          {trustItems.map((item) => <p key={item}><ShieldCheck size={17} />{item}</p>)}
        </div>
      </Section>

      <Section eyebrow="Данные" title="Суверенитет данных и соответствие 152-ФЗ">
        <p className="landing-lead">
          AI-Arbitr следует принципу минимизации персональных данных: полные реквизиты нужны только для формирования
          финального PDF и отправки сторонам. Для аналитики используются агрегированные и обезличенные признаки.
        </p>
        <div className="landing-note">Ваши документы и история должны оставаться под вашим контролем, без вендор-локина.</div>
      </Section>

      <Section eyebrow="Команда" title="Команда AI-Arbitr">
        <div className="landing-team">
          {team.map(([name, role]) => (
            <article key={name}>
              <span>{name.slice(0, 1)}</span>
              <strong>{name}</strong>
              <p>{role}</p>
              <div><a>Max</a><a>TG</a><a>WA</a><a>VK</a></div>
            </article>
          ))}
        </div>
      </Section>

      <Section eyebrow="Roadmap" title="AI-Arbitr сегодня и завтра">
        <div className="landing-roadmap">
          {roadmap.map(([date, text]) => <article key={`${date}-${text}`}><strong>{date}</strong><p>{text}</p></article>)}
        </div>
        <div className="landing-future-cycle">
          <div>
            <span>План развития экосистемы</span>
            <h3>От договора до фактического взыскания</h3>
            <p>
              В перспективе AI-Arbitr должен связать договор, исполнение, страховую защиту и работу
              доверенных юристов в единый последовательный процесс.
            </p>
          </div>
          <ol>
            {futureCycle.map((step, index) => (
              <li key={step}><span>{index + 1}</span>{step}</li>
            ))}
          </ol>
          <small>
            Эскроу, страхование, рейтинги и регрессное взыскание не входят в текущую MVP-версию и указаны как планы развития.
          </small>
        </div>
      </Section>

      <Section eyebrow="FAQ" title="Часто задаваемые вопросы" className="landing-faq" >
        <div id="faq" className="landing-faq-list">
          {faq.map(([question, answer]) => (
            <details key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </Section>

      <section className="landing-final">
        <h2>Готовы заключить договор за 5 минут?</h2>
        <p>Без юристов. Без судов. Без бюрократии. Бесплатно навсегда для физлиц, самозанятых, ИП и МСП.</p>
        <a className="landing-primary" href={appHref}>Начать бесплатно <ArrowRight size={18} /></a>
        <small>iPhone или Android | С VPN или без | Без ввода карты | Попробуйте без регистрации</small>
      </section>
    </main>
  );
}
