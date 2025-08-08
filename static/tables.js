// Modern Table Management System
class TableManager {
  constructor(tableName, initialPageNum = 1) {
    this.tableName = tableName.toLowerCase();
    this.currentPage = initialPageNum;
    this.selectedRows = new Set();
    this.lastClickedRow = null;
    this.tableData = null;
    this.inputOptions = null;
    
    // DOM elements
    this.tableBody = document.querySelector('tbody');
    this.reviseButton = document.getElementById('ReviseButton');
    this.removeButton = document.getElementById('RemoveButton');
    
    this.initialize();
  }

  async initialize() {
    try {
      // Input options will be loaded lazily when needed
      
      // Check if table data is already loaded (drill-down mode)
      const existingRows = document.querySelectorAll('.modern-table tbody tr:not(.no-data-row)');
      if (existingRows.length > 0 && !existingRows[0].classList.contains('jsTableRow')) {
        // Pre-loaded data exists but doesn't have proper classes, let's fix it
        existingRows.forEach((row, index) => {
          row.classList.add('jsTableRow');
          if (!row.dataset.index) {
            row.dataset.index = index.toString();
          }
        });
      }
      
      if (existingRows.length > 0) {
        // Derive current page from rendered page info if available
        const pageInfoEl = document.querySelector('.page-info');
        if (pageInfoEl && pageInfoEl.textContent) {
          const match = pageInfoEl.textContent.match(/Page\s+(\d+)/i);
          if (match) {
            this.currentPage = parseInt(match[1], 10) || this.currentPage;
          }
        } else {
          // Fallback to URL path parsing: /table/<table>/<page>
          const parts = window.location.pathname.split('/').filter(Boolean);
          if (parts.length === 3 && parts[0] === 'table') {
            const maybePage = parseInt(parts[2], 10);
            if (!Number.isNaN(maybePage)) this.currentPage = maybePage;
          }
        }
        // We have pre-loaded data (drill-down mode), just set up interactions
        this.setupEventListeners();
        this.updateButtonStates();
        this.setupPaginationForPreloadedData();
        this.setupPaginationListeners();
      } else {
        // Load initial table data dynamically
        await this.loadTableData(this.currentPage);
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Update button states
        this.updateButtonStates();
        
        // Setup pagination listeners
        this.setupPaginationListeners();
      }
      
    } catch (error) {
      console.error('Error initializing table manager:', error);
      this.showError('Failed to initialize table');
    }
  }

  async loadInputOptions() {
    // Only load if not already loaded
    if (this.inputOptions) return;
    
    try {
      const response = await fetch('/input_options');
      if (!response.ok) throw new Error('Failed to load input options');
      this.inputOptions = await response.json();
    } catch (error) {
      console.error('Error loading input options:', error);
      // Set empty object to prevent repeated failures
      this.inputOptions = {};
      throw error;
    }
  }

  async loadTableData(pageNum, isDrillDown = false, rowId = null, gameNum = 0) {
    try {
      showProcessingModal('Loading table data...');
      
      let url;
      if (isDrillDown) {
        url = `/api/table/${this.tableName}/drill/${rowId}/${gameNum}`;
      } else {
        url = `/api/table/${this.tableName}/${pageNum}`;
      }
      
      const response = await fetch(url, {
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to load table data');
      }

      this.tableData = await response.json();
      this.currentPage = this.tableData.page_num || 1;
      
      hideProcessingModal();
      
      // Update table display
      this.renderTable();
      this.updatePagination();
      this.clearSelection();
      this.setupPaginationListeners();
      
    } catch (error) {
      hideProcessingModal();
      console.error('Error loading table data:', error);
      this.showError('Failed to load table data');
    }
  }

  renderTable() {
    if (!this.tableData || !this.tableData.data) {
      this.tableBody.innerHTML = '<tr><td colspan="100%" class="text-center">No data available</td></tr>';
      return;
    }

    const rows = this.tableData.data.map((row, index) => {
      const rowId = `row${index + 1}`;
      return this.createTableRow(row, rowId, index);
    }).join('');

    this.tableBody.innerHTML = rows;
    
    // Add hover effect for drillable tables
    if (['matches', 'games', 'drafts'].includes(this.tableName)) {
      this.tableBody.style.cursor = 'pointer';
      this.tableBody.title = 'Double-click to drill-down';
    }
  }

  createTableRow(row, rowId, index) {
    const columns = this.getColumnsForTable(row);
    const columnHtml = columns.map(col => `<td class="text-center td-small">${col}</td>`).join('');
    
    // Store essential data in data attributes for reliable access
    const dataAttrs = this.getDataAttributes(row);
    
    return `<tr class="jsTableRow" id="${rowId}" data-index="${index}" ${dataAttrs}>${columnHtml}</tr>`;
  }
  
  getDataAttributes(row) {
    switch (this.tableName) {
      case 'matches':
        return `data-match-id="${row.match_id}" data-draft-id="${row.draft_id}"`;
      case 'games':
        return `data-match-id="${row.match_id}" data-game-num="${row.game_num}"`;
      case 'drafts':
        return `data-draft-id="${row.draft_id}"`;
      case 'plays':
        return `data-match-id="${row.match_id}" data-game-num="${row.game_num}"`;
      case 'picks':
        return `data-draft-id="${row.draft_id}"`;
      default:
        return '';
    }
  }

  getColumnsForTable(row) {
    switch (this.tableName) {
      case 'matches':
        return [
          row.draft_id, row.p1, row.p1_arch, row.p1_subarch,
          row.p2, row.p2_arch, row.p2_subarch, row.p1_roll, row.p2_roll,
          row.roll_winner, row.p1_wins, row.p2_wins, row.match_winner,
          row.format, row.match_type, row.date
        ];
      case 'games':
        return [
          row.p1, row.p2, row.game_num, row.pd_selector,
          row.pd_choice, row.on_play, row.on_draw, row.p1_mulls, row.p2_mulls,
          row.turns, row.game_winner
        ];
      case 'plays':
        return [
          row.game_num, row.play_num, row.turn_num, row.casting_player,
          row.action, row.primary_card, row.target1, row.target2, row.target3,
          row.opp_target, row.self_target, row.cards_drawn, row.attackers,
          row.active_player, row.non_active_player
        ];
      case 'drafts':
        return [
          row.hero, row.player2, row.player3, row.player4,
          row.player5, row.player6, row.player7, row.player8, row.match_wins,
          row.match_losses, row.format, row.date
        ];
      case 'picks':
        return [
          row.card, row.pack_num, row.pick_num, row.pick_ovr, row.avail1,
          row.avail2, row.avail3, row.avail4, row.avail5, row.avail6,
          row.avail7, row.avail8, row.avail9, row.avail10, row.avail11,
          row.avail12, row.avail13, row.avail14
        ];
      default:
        return Object.values(row);
    }
  }

  setupEventListeners() {
    console.log('TableManager: Setting up event listeners');
    console.log('TableManager: tableBody:', this.tableBody);
    console.log('TableManager: reviseButton:', this.reviseButton);
    console.log('TableManager: removeButton:', this.removeButton);
    
    // Row click handling (single, ctrl, shift)
    if (this.tableBody) {
      this.tableBody.addEventListener('click', (e) => {
        const row = e.target.closest('.jsTableRow');
        if (!row) return;
        
        console.log('TableManager: Row clicked:', row);
        this.handleRowClick(row, e);
      });

      // Double-click for drill-down
      this.tableBody.addEventListener('dblclick', (e) => {
        const row = e.target.closest('.jsTableRow');
        if (!row) return;
        
        this.handleRowDoubleClick(row);
      });
    }

    // Button event listeners
    if (this.reviseButton) {
      console.log('TableManager: Adding click listener to revise button');
      this.reviseButton.addEventListener('click', (e) => {
        console.log('TableManager: Revise button clicked!');
        e.preventDefault();
        this.openReviseModal();
      });
    } else {
      console.log('TableManager: No revise button found');
    }

    if (this.removeButton) {
      this.removeButton.addEventListener('click', (e) => {
        e.preventDefault();
        this.openRemoveModal();
      });
    }
  }

  handleRowClick(row, event) {
    const rowIndex = parseInt(row.dataset.index);
    
    if (event.shiftKey && this.lastClickedRow !== null) {
      // Shift+click: select range
      this.selectRange(this.lastClickedRow, rowIndex);
    } else if (event.ctrlKey || event.metaKey) {
      // Ctrl+click: toggle single row
      this.toggleRowSelection(row, rowIndex);
    } else {
      // Normal click: select single row
      this.clearSelection();
      this.selectRow(row, rowIndex);
      this.lastClickedRow = rowIndex;
    }

    this.updateButtonStates();
    
    // Load match details for single selection (matches table only)
    if (this.tableName === 'matches' && this.selectedRows.size === 1) {
      const selectedData = this.getSelectedRowData()[0];
      this.loadMatchDetails(selectedData.match_id);
    }
  }

  handleRowDoubleClick(row) {
    // Get row data from API data or from DOM
    let rowData;
    if (this.tableData && this.tableData.data) {
      rowData = this.tableData.data[parseInt(row.dataset.index)];
    } else {
      // Extract data from DOM (drill-down mode)
      rowData = this.extractRowDataFromDOM(row);
    }
    
    if (!rowData) {
      console.log('No row data available for drill down');
      return;
    }
    
    // Determine drill-down target
    let targetTable, rowId, gameNum = 0;
    
    switch (this.tableName) {
      case 'matches':
        targetTable = 'games';
        rowId = rowData.match_id;
        break;
      case 'games':
        targetTable = 'plays';
        rowId = rowData.match_id;
        gameNum = rowData.game_num;
        break;
      case 'drafts':
        targetTable = 'picks';
        rowId = rowData.draft_id;
        break;
      default:
        return; // No drill-down available
    }


    // Navigate to drill-down table
    window.location.href = `/table/${targetTable}/${rowId}/${gameNum}`;
  }

  extractRowDataFromDOM(row) {
    // Use data attributes for reliable data access (independent of visible columns)
    switch (this.tableName) {
      case 'matches':
        return {
          match_id: row.dataset.matchId,
          draft_id: row.dataset.draftId,
          // Other fields can be added as needed
        };
      case 'games':
        return {
          match_id: row.dataset.matchId,
          game_num: row.dataset.gameNum,
          // Other fields can be added as needed
        };
      case 'drafts':
        return {
          draft_id: row.dataset.draftId,
          // Other fields can be added as needed
        };
      case 'plays':
        return {
          match_id: row.dataset.matchId,
          game_num: row.dataset.gameNum,
          // Other fields can be added as needed
        };
      case 'picks':
        return {
          draft_id: row.dataset.draftId,
          // Other fields can be added as needed
        };
      default:
        return null;
    }
  }

  selectRow(row, index) {
    row.classList.add('selected');
    this.selectedRows.add(index);
  }

  toggleRowSelection(row, index) {
    if (this.selectedRows.has(index)) {
      row.classList.remove('selected');
      this.selectedRows.delete(index);
    } else {
      row.classList.add('selected');
      this.selectedRows.add(index);
    }
  }

  selectRange(startIndex, endIndex) {
    const start = Math.min(startIndex, endIndex);
    const end = Math.max(startIndex, endIndex);
    
    for (let i = start; i <= end; i++) {
      const row = document.querySelector(`[data-index="${i}"]`);
      if (row) {
        this.selectRow(row, i);
      }
    }
  }

  clearSelection() {
    document.querySelectorAll('.jsTableRow.selected').forEach(row => {
      row.classList.remove('selected');
    });
    this.selectedRows.clear();
  }

  getSelectedRowData() {
    if (this.tableData && this.tableData.data) {
      return Array.from(this.selectedRows).map(index => this.tableData.data[index]);
    } else {
      // Extract data from DOM (drill-down mode)
      return Array.from(this.selectedRows).map(index => {
        const row = document.querySelector(`[data-index="${index}"]`);
        return row ? this.extractRowDataFromDOM(row) : null;
      }).filter(data => data !== null);
    }
  }

  updateButtonStates() {
    if (!this.reviseButton || !this.removeButton) return;

    const selectionCount = this.selectedRows.size;
    
    if (selectionCount === 0) {
      this.reviseButton.disabled = true;
      this.removeButton.disabled = true;
    } else {
      this.reviseButton.disabled = false;
      this.removeButton.disabled = false;
    }
  }

  async loadMatchDetails(matchId) {
    if (this.tableName !== 'matches') return;
    
    try {
      const response = await fetch(`/api/match/${matchId}/details`, {
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) return;

      const matchData = await response.json();
      await this.populateReviseModal(matchData);
      
    } catch (error) {
      console.error('Error loading match details:', error);
    }
  }

  async populateReviseModal(data) {
    // Store original form values for reset functionality
    if (typeof originalFormValues !== 'undefined') {
      originalFormValues = {
        p1_arch: data.p1_arch,
        p1_subarch: data.p1_subarch,
        p2_arch: data.p2_arch,
        p2_subarch: data.p2_subarch,
        format: data.format,
        match_type: data.match_type
      };
    }

    // Update match ID
    const modalMatchId = document.getElementById('ModalMatchId');
    if (modalMatchId) {
      modalMatchId.innerHTML = `<center><b>Match ID:</b> ${data.match_id}<br><b>Date:</b> ${data.date}</center>`;
    }

    // Update players and card lists
    const modalP1 = document.getElementById('ModalP1');
    const modalP2 = document.getElementById('ModalP2');
    const revisePlays1 = document.getElementById('RevisePlays1');
    const revisePlays2 = document.getElementById('RevisePlays2');
    const reviseLands1 = document.getElementById('ReviseLands1');
    const reviseLands2 = document.getElementById('ReviseLands2');

    if (modalP1 && modalP2) {
      // Use p1 and p2 from match data as primary source of truth
      const player1 = data.p1 || 'Player 1';
      const player2 = data.p2 || 'Player 2';
      
      modalP1.innerHTML = `<b>P1: ${player1}</b>`;
      modalP2.innerHTML = `<b>P2: ${player2}</b>`;
      
      // For card lists, use casting_player data if available, otherwise use p1/p2 mapping
      let plays1Data = [];
      let plays2Data = [];
      let lands1Data = [];
      let lands2Data = [];
      
      if (data.casting_player1 && data.casting_player2) {
        // Check which casting player corresponds to which position
        if (data.p1 === data.casting_player1) {
          plays1Data = data.plays1 || [];
          plays2Data = data.plays2 || [];
          lands1Data = data.lands1 || [];
          lands2Data = data.lands2 || [];
        } else {
          // Swap the data if casting players are reversed
          plays1Data = data.plays2 || [];
          plays2Data = data.plays1 || [];
          lands1Data = data.lands2 || [];
          lands2Data = data.lands1 || [];
        }
      } else {
        // Fallback to direct mapping if casting player data is not available
        plays1Data = data.plays1 || [];
        plays2Data = data.plays2 || [];
        lands1Data = data.lands1 || [];
        lands2Data = data.lands2 || [];
      }
      
      if (revisePlays1) revisePlays1.innerHTML = plays1Data.join('<br>');
      if (revisePlays2) revisePlays2.innerHTML = plays2Data.join('<br>');
      if (reviseLands1) reviseLands1.innerHTML = lands1Data.join('<br>');
      if (reviseLands2) reviseLands2.innerHTML = lands2Data.join('<br>');
    }

    // Update form fields
    this.updateDropdownValue('P1ArchButton', data.p1_arch);
    this.updateDropdownValue('P2ArchButton', data.p2_arch);
    this.updateDropdownValue('FormatButton', data.format);
    this.updateDropdownValue('MatchTypeButton', data.match_type);

    // Update text inputs
    const p1SubarchInput = document.getElementById('P1_Subarch');
    const p2SubarchInput = document.getElementById('P2_Subarch');
    
    if (p1SubarchInput) p1SubarchInput.value = data.p1_subarch || 'NA';
    if (p2SubarchInput) p2SubarchInput.value = data.p2_subarch || 'NA';

    // Handle format-specific UI changes
    await this.handleFormatChange(data.format);
  }

  updateDropdownValue(buttonId, value) {
    const button = document.getElementById(buttonId);
    if (button) {
      const span = button.querySelector('span');
      if (span) {
        // New structure with span and icon
        span.textContent = value || 'NA';
      } else {
        // Fallback for old structure
        button.textContent = value || 'NA';
      }
    }
  }

  async handleFormatChange(format) {
    const p1ArchButton = document.getElementById('P1ArchButton');
    const p2ArchButton = document.getElementById('P2ArchButton');

    // Ensure input options are loaded
    await this.loadInputOptions();
    if (!this.inputOptions) return;

    if (this.inputOptions['Limited Formats']?.includes(format)) {
      // Limited format
      if (p1ArchButton) {
        p1ArchButton.disabled = true;
        const span = p1ArchButton.querySelector('span');
        if (span) {
          span.textContent = 'Limited';
        } else {
          p1ArchButton.textContent = 'Limited';
        }
      }
      if (p2ArchButton) {
        p2ArchButton.disabled = true;
        const span = p2ArchButton.querySelector('span');
        if (span) {
          span.textContent = 'Limited';
        } else {
          p2ArchButton.textContent = 'Limited';
        }
      }
    } else {
      // Constructed format
      if (p1ArchButton) {
        p1ArchButton.disabled = false;
      }
      if (p2ArchButton) {
        p2ArchButton.disabled = false;
      }
    }
  }

  async openReviseModal() {
    console.log('TableManager: openReviseModal called');
    const selectedData = this.getSelectedRowData();
    console.log('TableManager: selectedData:', selectedData);
    if (selectedData.length === 0) {
      console.log('TableManager: No rows selected, returning');
      return;
    }

    if (selectedData.length === 1) {
      console.log('TableManager: Single row selected, showing single revision modal');
      // Single revision modal is already populated by loadMatchDetails
      await this.showReviseModal();
    } else {
      console.log('TableManager: Multiple rows selected, showing multi revision modal');
      // Multi revision modal
      await this.showReviseMultiModal();
    }
  }

  async openRemoveModal() {
    const selectedData = this.getSelectedRowData();
    if (selectedData.length === 0) return;

    this.showRemoveModal();
  }

  async showReviseModal() {
    await this.populateDropdownMenus();
    const modal = document.getElementById('ReviseModal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }

  async showReviseMultiModal() {
    await this.populateDropdownMenus();
    
    // Initialize field container visibility (default is P1 Deck)
    this.initializeMultiModalFields();
    
    const modal = document.getElementById('ReviseMultiModal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }

  initializeMultiModalFields() {
    // Reset Step 1 button to default "P1 Deck"
    const fieldToChangeButton = document.getElementById("FieldToChangeButton");
    if (fieldToChangeButton) {
      fieldToChangeButton.innerHTML = "P1 Deck";
    }
    
    // Default selection is "P1 Deck", so show only P1FieldsContainer
    const p1Container = document.getElementById("P1FieldsContainer");
    const p2Container = document.getElementById("P2FieldsContainer");
    const formatContainer = document.getElementById("FormatFieldsContainer");
    const matchTypeContainer = document.getElementById("MatchTypeFieldsContainer");
    
    if (p1Container) p1Container.style.display = 'block';
    if (p2Container) p2Container.style.display = 'none';
    if (formatContainer) formatContainer.style.display = 'none';
    if (matchTypeContainer) matchTypeContainer.style.display = 'none';
  }

  async populateDropdownMenus() {
    // Ensure input options are loaded
    await this.loadInputOptions();
    if (!this.inputOptions) return;

    // Populate archetype dropdowns
    const archetypes = [
      ...(this.inputOptions['Archetypes'] || []),
      'NA'
    ];
    this.populateDropdownMenu('P1ArchMenu', archetypes, 'showP1Arch');
    this.populateDropdownMenu('P2ArchMenu', archetypes, 'showP2Arch');
    this.populateDropdownMenu('P1ArchMenuMulti', archetypes, 'showP1ArchMulti');
    this.populateDropdownMenu('P2ArchMenuMulti', archetypes, 'showP2ArchMulti');

    // Populate format dropdowns
    const allFormats = [
      ...(this.inputOptions['Constructed Formats'] || []),
      ...(this.inputOptions['Limited Formats'] || []),
      'NA'
    ];
    this.populateDropdownMenu('FormatMenu', allFormats, 'showFormat');
    this.populateDropdownMenu('FormatMenuMulti', allFormats, 'showFormatMulti');

    // Populate match type dropdowns
    const allMatchTypes = [
      ...(this.inputOptions['Constructed Match Types'] || []),
      ...(this.inputOptions['Booster Draft Match Types'] || []),
      ...(this.inputOptions['Sealed Match Types'] || []),
      'NA'
    ];
    this.populateDropdownMenu('MatchTypeMenu', allMatchTypes, 'showMatchType');
    this.populateDropdownMenu('MatchTypeMenuMulti', allMatchTypes, 'showMatchTypeMulti');
  }

  populateDropdownMenu(menuId, items, clickHandler) {
    const menu = document.getElementById(menuId);
    if (!menu) return;

    menu.innerHTML = items.map(item => 
      `<li onclick="${clickHandler}(this)">${item}</li>`
    ).join('');
  }

  showRemoveModal() {
    const modal = document.getElementById('RemoveModal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }

  async submitRevision(formData) {
    try {
      const response = await fetch('/api/match/revise', {
        method: 'POST',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      const result = await response.json();

      if (result.success) {
        hideReviseModal();
        showFlashMessage(result.message, 'success');
        await this.loadTableData(this.currentPage);
      } else {
        showFlashMessage(result.error || 'Failed to update record', 'error');
      }

    } catch (error) {
      console.error('Error submitting revision:', error);
      showFlashMessage('Failed to update record', 'error');
    }
  }

  async submitMultiRevision(formData) {
    try {
      const response = await fetch('/api/match/revise-multi', {
        method: 'POST',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      const result = await response.json();

      if (result.success) {
        hideReviseMultiModal();
        showFlashMessage(result.message, 'success');
        await this.loadTableData(this.currentPage);
      } else {
        showFlashMessage(result.error || 'Failed to update records', 'error');
      }

    } catch (error) {
      console.error('Error submitting multi revision:', error);
      showFlashMessage('Failed to update records', 'error');
    }
  }

  async submitRemoval(removeType) {
    try {
      const selectedData = this.getSelectedRowData();
      const matchIds = selectedData.map(row => row.match_id);

      const response = await fetch('/api/match/remove', {
        method: 'POST',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          match_ids: matchIds,
          remove_type: removeType
        })
      });

      const result = await response.json();

      if (result.success) {
        hideRemoveModal();
        showFlashMessage(result.message, 'success');
        await this.loadTableData(this.currentPage);
      } else {
        showFlashMessage(result.error || 'Failed to remove records', 'error');
      }

    } catch (error) {
      console.error('Error removing records:', error);
      showFlashMessage('Failed to remove records', 'error');
    }
  }

  updatePagination() {
    if (!this.tableData) return;

    const { page_num, total_pages, has_previous, has_next } = this.tableData;

    // Update pagination controls (if they exist)
    const prevButton = document.getElementById('PrevButton');
    const nextButton = document.getElementById('NextButton');
    const pageInfo = document.querySelector('.page-info');

    if (prevButton) {
      prevButton.disabled = !has_previous;
      prevButton.onclick = has_previous ? () => this.loadTableData(page_num - 1) : null;
    }

    if (nextButton) {
      nextButton.disabled = !has_next;
      nextButton.onclick = has_next ? () => this.loadTableData(page_num + 1) : null;
    }

    if (pageInfo) {
      pageInfo.textContent = `Page ${page_num} of ${total_pages}`;
    }
  }

  setupPaginationForPreloadedData() {
    // Only hide pagination if we're in drill-down mode (URL has 4+ segments)
    const urlParts = window.location.pathname.split('/').filter(part => part.length > 0);
    const isDrillDownMode = urlParts.length >= 4; // e.g., /table/games/MATCH123/0
    
    if (isDrillDownMode) {
      const paginationContainer = document.querySelector('.pagination-container');
      if (paginationContainer) {
        paginationContainer.style.display = 'none';
      }
    }
  }

  setupPaginationListeners() {
    // Set up event listeners for pagination buttons in case they don't have onclick
    const prevButton = document.getElementById('PrevButton');
    const nextButton = document.getElementById('NextButton');
    
    if (prevButton && !prevButton.onclick && !prevButton.disabled) {
      const currentPage = parseInt(this.currentPage);
      if (currentPage > 1) {
        prevButton.addEventListener('click', () => {
          window.location.href = `/table/${this.tableName}/${currentPage - 1}`;
        });
      }
    }
    
    if (nextButton && !nextButton.onclick && !nextButton.disabled) {
      const currentPage = parseInt(this.currentPage);
      const totalPages = this.tableData?.total_pages || parseInt(document.querySelector('.page-info span')?.textContent?.match(/of (\d+)/)?.[1]) || 1;
      if (currentPage < totalPages) {
        nextButton.addEventListener('click', () => {
          window.location.href = `/table/${this.tableName}/${currentPage + 1}`;
        });
      }
    }
  }

  showError(message) {
    if (typeof showFlashMessage === 'function') {
      showFlashMessage(message, 'error');
    } else {
      alert(message);
    }
  }
}

// Global navigation function for back button
function navigateBack() {
  const currentUrl = window.location.pathname;
  const urlParts = currentUrl.split('/').filter(part => part.length > 0);
  
  // urlParts structure: ['table', table_name, row_id, game_num] for drill-down
  // or ['table', table_name, page_num] for regular tables
  
  if (urlParts.length >= 4) {
    // This is a drill-down view, determine where to go back
    const tableName = urlParts[1];
    const rowId = urlParts[2];
    
    if (tableName === 'games') {
      // From games filtered by match → back to matches table
      window.location.href = '/table/matches/1';
    } else if (tableName === 'plays') {
      // From plays filtered by game → back to games filtered by same match
      window.location.href = `/table/games/${rowId}/0`;
    } else if (tableName === 'picks') {
      // From picks filtered by draft → back to drafts table
      window.location.href = '/table/drafts/1';
    }
  } else {
    // Fallback - shouldn't happen in normal usage
    window.history.back();
  }
}

// Global table manager instance
let tableManager = null;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  console.log('TableManager: DOMContentLoaded event fired');
  const tableNameElement = document.getElementById('tname');
  console.log('TableManager: tname element:', tableNameElement);
  if (tableNameElement) {
    const tableName = tableNameElement.value;
    // Prefer path segment for page number: /table/<table>/<page>
    let pageNum = parseInt(new URLSearchParams(window.location.search).get('page'));
    if (Number.isNaN(pageNum) || !pageNum) {
      const parts = window.location.pathname.split('/').filter(Boolean);
      if (parts.length === 3 && parts[0] === 'table' && parts[1] === tableName) {
        const maybePage = parseInt(parts[2], 10);
        if (!Number.isNaN(maybePage)) pageNum = maybePage;
      }
    }
    if (Number.isNaN(pageNum) || !pageNum) pageNum = 1;
    console.log('TableManager: Initializing with table:', tableName, 'page:', pageNum);
    
    tableManager = new TableManager(tableName, pageNum);
    console.log('TableManager: Instance created:', tableManager);
  } else {
    console.log('TableManager: No tname element found');
  }
});

// Legacy function compatibility for existing modal forms
function changeHiddenInputs() {
  if (!tableManager) return;
  
  const selectedData = tableManager.getSelectedRowData()[0];
  if (!selectedData) return;

  const formData = {
    match_id: selectedData.match_id,
    p1_arch: document.getElementById('P1ArchButton')?.textContent,
    p1_subarch: document.getElementById('P1_Subarch')?.value,
    p2_arch: document.getElementById('P2ArchButton')?.textContent,
    p2_subarch: document.getElementById('P2_Subarch')?.value,
    format: document.getElementById('FormatButton')?.textContent,
    match_type: document.getElementById('MatchTypeButton')?.textContent
  };

  tableManager.submitRevision(formData);
}

function changeHiddenInputsMulti() {
  if (!tableManager) return;
  
  const selectedData = tableManager.getSelectedRowData();
  const matchIds = selectedData.map(row => row.match_id);

  // Helper function to get clean text content from buttons
  function getButtonText(buttonId) {
    const button = document.getElementById(buttonId);
    if (!button) return null;
    
    // Check for new structure with span element
    const span = button.querySelector('span');
    if (span) {
      return span.textContent?.trim() || span.innerText?.trim() || null;
    }
    
    // Fallback to old structure
    return button.textContent?.trim() || button.innerText?.trim() || null;
  }

  const formData = {
    match_ids: matchIds,
    field_to_change: getButtonText('FieldToChangeButton'),
    p1_arch: getButtonText('P1ArchButtonMulti'),
    p1_subarch: document.getElementById('P1_Subarch_Multi')?.value?.trim(),
    p2_arch: getButtonText('P2ArchButtonMulti'),
    p2_subarch: document.getElementById('P2_Subarch_Multi')?.value?.trim(),
    format: getButtonText('FormatButtonMulti'),
    match_type: getButtonText('MatchTypeButtonMulti')
  };

  // Debug logging to see what data is being sent
  console.log('Multi-revision form data:', formData);

  tableManager.submitMultiRevision(formData);
}

function removeHidden(removeType) {
  if (!tableManager) return;
  
  tableManager.submitRemoval(removeType);
  return true;
}

// Helper function to close all dropdowns
function closeAllDropdowns() {
  document.querySelectorAll('.dropdown-menu').forEach(menu => {
    menu.classList.remove('show');
    // Reset positioning styles
    menu.style.left = '';
    menu.style.top = '';
    menu.style.position = '';
  });
  document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
    toggle.classList.remove('active');
  });
}

// Dropdown helper functions (keeping compatibility with existing modals)
function showP1Arch(item) { 
  const button = document.getElementById("P1ArchButton");
  const span = button.querySelector('span');
  if (span) {
    span.textContent = item.textContent;
  } else {
    button.innerHTML = item.innerHTML;
  }
  closeAllDropdowns();
}
function showP2Arch(item) { 
  const button = document.getElementById("P2ArchButton");
  const span = button.querySelector('span');
  if (span) {
    span.textContent = item.textContent;
  } else {
    button.innerHTML = item.innerHTML;
  }
  closeAllDropdowns();
}
function showFormat(item) { 
  const button = document.getElementById("FormatButton");
  const span = button.querySelector('span');
  if (span) {
    span.textContent = item.textContent;
  } else {
    button.innerHTML = item.innerHTML;
  }
  closeAllDropdowns();
  if (tableManager) {
    // Fire and forget - don't block UI
    tableManager.handleFormatChange(item.innerHTML).catch(err => 
      console.error('Error handling format change:', err)
    );
  }
}

function showMatchType(item) { 
  const button = document.getElementById("MatchTypeButton");
  const span = button.querySelector('span');
  if (span) {
    span.textContent = item.textContent;
  } else {
    button.innerHTML = item.innerHTML;
  }
  closeAllDropdowns();
}

function showP1ArchMulti(item) { 
  document.getElementById("P1ArchButtonMulti").innerHTML = item.innerHTML;
  closeAllDropdowns();
}
function showP2ArchMulti(item) { 
  document.getElementById("P2ArchButtonMulti").innerHTML = item.innerHTML;
  closeAllDropdowns();
}
function showFormatMulti(item) { 
  document.getElementById("FormatButtonMulti").innerHTML = item.innerHTML;
  closeAllDropdowns();
}
function showMatchTypeMulti(item) { 
  document.getElementById("MatchTypeButtonMulti").innerHTML = item.innerHTML;
  closeAllDropdowns();
}

// Multi-modal field switching functions
function showP1Field(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  closeAllDropdowns();
  
  // Show P1 container, hide all others
  document.getElementById("P1FieldsContainer").style.display = 'block';
  document.getElementById("P2FieldsContainer").style.display = 'none';
  document.getElementById("FormatFieldsContainer").style.display = 'none';
  document.getElementById("MatchTypeFieldsContainer").style.display = 'none';
}

function showP2Field(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  closeAllDropdowns();
  
  // Show P2 container, hide all others
  document.getElementById("P1FieldsContainer").style.display = 'none';
  document.getElementById("P2FieldsContainer").style.display = 'block';
  document.getElementById("FormatFieldsContainer").style.display = 'none';
  document.getElementById("MatchTypeFieldsContainer").style.display = 'none';
}

function showFormatField(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  closeAllDropdowns();
  
  // Show format container, hide all others
  document.getElementById("P1FieldsContainer").style.display = 'none';
  document.getElementById("P2FieldsContainer").style.display = 'none';
  document.getElementById("FormatFieldsContainer").style.display = 'block';
  document.getElementById("MatchTypeFieldsContainer").style.display = 'none';
}

function showMatchTypeField(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  closeAllDropdowns();
  
  // Show match type container, hide all others
  document.getElementById("P1FieldsContainer").style.display = 'none';
  document.getElementById("P2FieldsContainer").style.display = 'none';
  document.getElementById("FormatFieldsContainer").style.display = 'none';
  document.getElementById("MatchTypeFieldsContainer").style.display = 'block';
}