// AJAX incremental search front-end
// Binds to the search input (#q) and performs debounced calls to /api/search
(function(){
  const input = document.getElementById('q');
  if(!input) return;

  const username = input.getAttribute('data-username') || '';
  const perPageSelect = document.getElementById('per_page_select');
  const spinner = document.getElementById('search-spinner');
  const errorBox = document.getElementById('search-error');

  let currentPage = 1;
  let currentPerPage = perPageSelect ? parseInt(perPageSelect.value) : 20;

  const resultsContainer = document.getElementById('items-table');
  const paginationContainer = document.querySelector('.pagination');

  function showSpinner(){ if(spinner) spinner.style.display = 'inline-block'; }
  function hideSpinner(){ if(spinner) spinner.style.display = 'none'; }
  function showError(msg){ if(errorBox){ errorBox.style.display='block'; errorBox.textContent = msg; } }
  function hideError(){ if(errorBox){ errorBox.style.display='none'; errorBox.textContent = ''; } }

  function renderResults(resultJson){
    hideSpinner();
    hideError();
    // Support debug-wrapped payload
    if(resultJson && resultJson.result && resultJson.inspect){
      // debug endpoint returned wrapper
      // prefer the inner result
      resultJson = resultJson.result;
    }
    const items = resultJson.items || [];
    const total = resultJson.total || 0;
    const page = resultJson.page || 1;
    const per_page = resultJson.per_page || 20;
    currentPage = page;
    currentPerPage = per_page;

    const resultsRoot = document.getElementById('search-results');
    if(resultsRoot){
      // if there was no server-rendered table, create one inside resultsRoot
      if(!document.getElementById('items-table')){
        resultsRoot.innerHTML = `\n          <p id="search-counts">Showing 0 of 0 results</p>\n          <table class="table collapse show dataTable" id="items-table">\n            <thead><th>Item</th><th>Tags</th><th>Snippet</th></thead>\n            <tbody></tbody>\n          </table>\n          <nav aria-label="Search results pagination">\n            <ul class="pagination">\n              <li class="page-item"><a class="page-link" href="#" data-page="1" data-per_page="${per_page}">Previous</a></li>\n              <li class="page-item disabled"><a class="page-link">Page ${page}</a></li>\n              <li class="page-item"><a class="page-link" href="#" data-page="${page+1}" data-per_page="${per_page}">Next</a></li>\n            </ul>\n          </nav>\n        `;
      }
    }

    // find table and tbody
    const table = document.getElementById('items-table');
    if(!table) return;
    let tbody = table.querySelector('tbody');
    if(!tbody){
      tbody = document.createElement('tbody');
      table.appendChild(tbody);
    }
    tbody.innerHTML = '';

    for(const item of items){
      const tr = document.createElement('tr');
      const tdName = document.createElement('td');
      const a = document.createElement('a');
      let invSlug = (item.inventories && item.inventories[0] && item.inventories[0].slug) ? item.inventories[0].slug : '';
      // build link consistent with other route names
      a.href = `/items/@${encodeURIComponent(username)}/${encodeURIComponent(invSlug)}/${encodeURIComponent(item.slug)}`.replace('%40','@');
      a.textContent = item.name;
      tdName.appendChild(a);

      const tdTags = document.createElement('td');
      if(item.tags){
        for(const tag of item.tags.slice(0,5)){
          const span = document.createElement('span');
          span.className = 'badge bg-secondary me-1';
          span.textContent = tag;
          tdTags.appendChild(span);
        }
      }

      const tdSnippet = document.createElement('td');
      if(item.snippet){
        tdSnippet.innerHTML = item.snippet; // snippet is sanitized server-side
      } else {
        tdSnippet.innerHTML = '&nbsp;';
      }

      tr.appendChild(tdName);
      tr.appendChild(tdTags);
      tr.appendChild(tdSnippet);
      tbody.appendChild(tr);
    }

    // update counts and pagination
    const showingText = document.querySelector('#search-counts');
    if(showingText){
      showingText.textContent = `Showing ${items.length} of ${total} results`;
    }

    // Update pagination links (data attributes)
    const pag = document.querySelector('.pagination');
    if(pag){
      const prevLi = pag.children[0];
      const pageLi = pag.children[1];
      const nextLi = pag.children[2];
      const prevA = prevLi.querySelector('a');
      const nextA = nextLi.querySelector('a');
      const prevPage = Math.max(1, page - 1);
      const nextPage = page + 1;
      prevA.setAttribute('data-page', prevPage);
      prevA.setAttribute('data-per_page', per_page);
      nextA.setAttribute('data-page', nextPage);
      nextA.setAttribute('data-per_page', per_page);

      if(page <= 1){ prevLi.classList.add('disabled'); } else { prevLi.classList.remove('disabled'); }
      if((page * per_page) >= total){ nextLi.classList.add('disabled'); } else { nextLi.classList.remove('disabled'); }

      pageLi.querySelector('a').textContent = `Page ${page}`;
    }
  }

  // debounce helper
  function debounce(fn, delay){
    let timer = null;
    return function(){
      clearTimeout(timer);
      timer = setTimeout(()=>fn.apply(this, arguments), delay);
    };
  }

  function buildUrl(q, page, per_page){
    const params = new URLSearchParams();
    if(q) params.set('q', q);
    if(page) params.set('page', page);
    if(per_page) params.set('per_page', per_page);
    return `${location.pathname}?${params.toString()}`;
  }

  async function doSearch(page=1, per_page=currentPerPage, pushState=true){
    const q = input.value.trim();
    if(!q) return;
    hideError();
    showSpinner();
    try{
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&page=${page}&per_page=${per_page}`, { credentials: 'same-origin' });
      if(!res.ok){
        const txt = await res.text();
        console.error('Search API error', res.status, txt);
        throw new Error(`Server returned ${res.status}`);
      }
      let json;
      try{
        json = await res.json();
      }catch(err){
        const txt = await res.text();
        console.error('Search API returned non-JSON response', txt);
        throw err;
      }
      renderResults(json);
      if(pushState){
        const url = buildUrl(q, page, per_page);
        history.pushState({q:q, page:page, per_page:per_page}, '', url);
      }
    }catch(err){
      hideSpinner();
      showError('Search failed — please try again.');
      console.error('Search AJAX error', err);
    }
  }

  // Debug query button
  const debugBtn = document.getElementById('debug-search-btn');
  const debugPre = document.getElementById('search-debug');
  if(debugBtn){
    debugBtn.addEventListener('click', async function(){
      const q = input.value.trim();
      if(!q){
        showError('Enter a query to debug');
        return;
      }
      hideError();
      showSpinner();
      try{
        // use combined debug endpoint that returns both result and inspect
        const res = await fetch(`/api/search_debug?q=${encodeURIComponent(q)}`, { credentials: 'same-origin' });
        if(!res.ok){
          const txt = await res.text();
          debugPre.style.display = 'block';
          debugPre.textContent = `Error ${res.status}: ${txt}`;
          hideSpinner();
          return;
        }
        const payload = await res.json();
        // payload: { result: {items,...}, inspect: {...} }
        debugPre.style.display = 'block';
        debugPre.textContent = JSON.stringify(payload.inspect, null, 2);
        if(payload.result){
          console.debug('Debug payload result', payload.result);
          // render the returned search result into the UI
          renderResults(payload.result);
        }
      }catch(err){
        debugPre.style.display = 'block';
        debugPre.textContent = 'Debug request failed';
        console.error('Debug inspect error', err);
      }finally{
        hideSpinner();
      }
    });
  }

  // Kick off search from state when navigating history
  window.addEventListener('popstate', function(evt){
    const state = evt.state || {};
    const q = state.q || new URLSearchParams(location.search).get('q') || '';
    const page = state.page || parseInt(new URLSearchParams(location.search).get('page')) || 1;
    const per_page = state.per_page || parseInt(new URLSearchParams(location.search).get('per_page')) || currentPerPage;
    input.value = q;
    if(perPageSelect) perPageSelect.value = per_page;
    doSearch(page, per_page, false);
  });

  input.addEventListener('input', debounce(()=>doSearch(1, parseInt(perPageSelect ? perPageSelect.value : currentPerPage)), 300));

  // intercept the form submit to perform AJAX search
  const form = input.closest('form');
  if(form){
    form.addEventListener('submit', function(evt){
      evt.preventDefault();
      const per_page = parseInt(perPageSelect ? perPageSelect.value : currentPerPage);
      doSearch(1, per_page);
    });
  }

  // update when per_page changes
  if(perPageSelect){
    perPageSelect.addEventListener('change', function(){
      const per = parseInt(perPageSelect.value);
      doSearch(1, per);
    });
  }

  // intercept pagination clicks
  document.addEventListener('click', function(evt){
    const a = evt.target.closest && evt.target.closest('.page-link');
    if(!a) return;
    const page = parseInt(a.getAttribute('data-page')) || 1;
    const per_page = parseInt(a.getAttribute('data-per_page')) || currentPerPage;
    if(a.getAttribute('href') === '#'){
      evt.preventDefault();
      doSearch(page, per_page);
    }
  });

  // On initial load, if q present in URL params, perform an AJAX search to hydrate
  (function initFromUrl(){
    const params = new URLSearchParams(location.search);
    const q = params.get('q');
    const page = parseInt(params.get('page')) || 1;
    const per_page = parseInt(params.get('per_page')) || currentPerPage;
    if(q){
      input.value = q;
      if(perPageSelect) perPageSelect.value = per_page;
      doSearch(page, per_page, false);
    }
  })();

})();
