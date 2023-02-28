var NODES = new vis.DataSet([])
var EDGES = new vis.DataSet([])

var DISTANCE = 3
var PRIORITIES = ['red', 'amber', 'yellow', 'green']
var TOPTEN = 0

var ALL_ELEMENTS = {
}

var ACTIVE_ELEMENTS = {
  nodes: new vis.DataSet([]),
  edges: new vis.DataSet([])
}

function htmlTitle(url, screenshot_url) {
  if (screenshot_url) {
      var html = "<div style='text-align: center; background-color: white; width:100%;height:100%;'>" +
        "<div style='width:120px;height:120px; overflow:hidden;'>" +
          "<img src='" + screenshot_url +
          "' style='width:120px;'> " +
        "</div>" +
      "</div>"
  } else {
    return ''
  }
  const container = document.createElement("div");
  container.innerHTML = html;
  return container;
}

var container = document.getElementById("mynetwork")
var options = {
  physics: {
      stabilization: {
          enabled: true,
          iterations: 125, // maximum number of iteration to stabilize
          updateInterval: 10,
          onlyDynamicEdges: false,
          fit: true
      },
  },
  interaction:{
    hover: true,
    tooltipDelay: 30,
  },
  nodes: {
    color: {
      hover: {
        border: 'black',
      },
      border: '#EEEEEE',
    },
    borderWidth: 1,
    shape: 'dot',
    scaling: {
      min: 6,
      max: 12,
    },
  },
  edges: {
    dashes: true,
    smooth: false,
    color: {
      color: '#E1E1E1',
    },
    chosen: {
      edge: function(values, id, selected, hovering) {
        values.dashes = false;
        values.width = 0.25;
        values.color = '#444444';
      },
    },
  },
  groups: {
    green: {
      color: {
        background: 'green',
      }
    },
    amber: {
      color: {
        background: 'orange',
      }
    },
    yellow: {
      color: {
        background: 'yellow',
      }
    },
    red: {
      label: '',
      color: {
        background: 'red',
      }
    },
    cluster: {
      value: 1,
      font: '20px arial black',
      shape: 'box',
      scaling: {
        min: 20,
        max: 24,
          label: {
            enabled: true,
            min: 20,
            max: 24,
            maxVisible: 32,
            drawThreshold: 5,
          },
      },
      color: {
        background: 'white',
      },
      chosen: {
        node: function(values, id, selected, hovering) {
          values.color = '#F1F1F1';
        },
      },
    }
  }
}

var network = new vis.Network(container, ACTIVE_ELEMENTS, options)
network.on('startStabilizing', forceStop);

function redrawMain() {
  network.stabilize()
  forceStop()
}

function forceStop() {
  setTimeout(function () {
    network.stopSimulation()
  }, 2.0 * 1000)
}

function buildNodes() {
  if (TOPTEN === 1) {
    nodes = ALL_ELEMENTS.nodes.filter(function(x) {
      return x.top_ten === 1
    })
    var copied_nodes = []
    for (let i = 0; i < nodes.length; i++) {
      node = JSON.parse(JSON.stringify(nodes[i]))
      node.shape = 'image'
      var url = `/image/${encodeURIComponent(node.screenshot_url.substr(18))}`
      node.image = url
      node.value = 80
      node.scaling = {min: 80, max: 80}
      delete node.title
      copied_nodes.push(node)
    }
    nodes = copied_nodes
  } else {
    nodes = ALL_ELEMENTS.nodes.filter(function(x) {
      return x.group === 'cluster' || (x.distance <= DISTANCE &&
        PRIORITIES.indexOf(x.group) > -1 )
    })
  }
  //
  //XXX reorder nodes
  ACTIVE_ELEMENTS.nodes.clear()
  ACTIVE_ELEMENTS.nodes.add(nodes)
  redrawMain()
  var static_results = $('.static-results-table tbody')
  static_results.empty()
  for (let i = 0; i < nodes.length; i++) {
    node = nodes[i]
    if (node.group === 'cluster') continue
    var row = $('<tr>')
    var cell = $('<td>') //icon
    var icon = $(`<div class='minor-icon minor-icon-${node.group}'>`)
    icon.appendTo(cell)
    cell.appendTo(row)
    cell = $(`<td><h2>${node.page_title}</h2>` +
      `<a href='${node.url}' target='_blank'>${node.url}</a></td>`) //XXX title or url
    cell.appendTo(row)
    cell = $('<td>') //wcag
    var line_container = $(`<span class='${node.a_techs ? 'fail' : 'pass'}-line'>`)
    var a_line = `Level A: ${node.a_diags ? 'FAIL' : 'PASS'} (${node.a_techs || 0} techniques, ${node.a_diags || 0} failures)<br>`
    line_container.html(a_line)
    cell.append(line_container)
    line_container = $(`<span class='${node.aa_techs ? 'fail' : 'pass'}-line'>`)
    var aa_line = `Level AA: ${node.aa_diags ? 'FAIL' : 'PASS'} (${node.aa_techs || 0} techniques, ${node.aa_diags || 0} failures)`
    line_container.html(aa_line)
    cell.append(line_container)
    cell.appendTo(row)
    cell = $('<td>') //axe
    line_container = $(`<span class='${node.axe_techs ? 'fail' : 'pass'}-line'>`)
    var axe_line = `${node.axe_diags ? 'FAIL' : 'PASS'} (${node.axe_techs || 0} techniques, ${node.axe_diags || 0} failures)`
    line_container.html(axe_line)
    cell.append(line_container)
    cell.appendTo(row)
    cell = $('<td>') //content editor
    line_container = $(`<span class='${node.red_techs ? 'fail' : 'pass'}-line'>`)
    var ce_line = `${node.red_diags ? 'FAIL' : 'PASS'} (${node.red_diags || 0} issues)`
    line_container.html(ce_line)
    cell.append(line_container)
    cell.appendTo(row)
    cell = $(`<td><button type="button" class="btn btn-primary">Check</button></td>`)
    cell.appendTo(row)
    row.appendTo(static_results)
  }
}

$(function() {

$("#distance1").click(function() {
  setTopTen(0)
  DISTANCE = 1
  buildNodes()
})
$("#distance2").click(function() {
  setTopTen(0)
  DISTANCE = 2
  buildNodes()
})
$("#distance3").click(function() {
  setTopTen(0)
  DISTANCE = 3
  buildNodes()
})
$(".distance-switch").click(function() {
  if ($(this).data('value') === 0) {
    $(".distance-switch").data('value', 0)
                   .removeClass('distance-switch-selected')
    $(this).data('value', 1)
                   .addClass('distance-switch-selected')
  }
})

$(".expand-horizontal").click(function() {
  if ( $('#text').hasClass('text-fat') ) {
    $('#text').removeClass('text-fat')
    $('#text').addClass('text-thin')
    $('#settings-header h2').hide()
    $('#chart-controls p').hide()
    $(".expand-horizontal-icon").addClass('contract-horizontal-icon')
  } else {
    $('#text').removeClass('text-thin')
    $('#text').addClass('text-fat')
    $('#settings-header h2').show()
    $('#chart-controls p').show()
    $(".expand-horizontal-icon").removeClass('contract-horizontal-icon')
  }
})

$.get('/json/vis/summary', function(data) {
  for (const id of ['ce', 'a', 'aa', 'axe']) {
    if (data[id + "_techs"]) $('.' + id + '-heading-line').addClass('fail-line')
    else $('.' + id + '-heading-line').addClass('pass-line')
    var line = `${data[id + "_techs"] ? 'FAIL' : 'PASS'} (${data[id + "_techs"]} techniques, ${data[id + "_diags"]} failures)`
    $('.' + id + '-heading-line').html(line)
  }


})

$.get('/json/vis/all', function(data) {
  for (var node of data.nodes) {
    if (node.url)
      node.title = htmlTitle(node.url, node.screenshot_url)
  }
  ALL_ELEMENTS = data
  ACTIVE_ELEMENTS.nodes.clear()
  ACTIVE_ELEMENTS.edges.clear()
  ACTIVE_ELEMENTS.nodes.add(data.nodes)
  ACTIVE_ELEMENTS.edges.add(data.edges)
  redrawMain()
  buildNodes()
  $("#chart-loading").hide()
  $(".expand-horizontal-icon").show()
  $("#settings-header").show()
  $("#chart-controls").show()
})

function updateToggleButton(toggle) {
  if (toggle.data('value') === 1)
    toggle.removeClass('empty-toggle')
  else
    toggle.addClass('empty-toggle')
}

function setTopTen(value=0) {
  $(".black-button").data('value', value)
  TOPTEN = value
  updateToggleButton($(".black-button"))
}

$(".black-button").click(function() {
  var value = $(this).data('value') === 0 ? 1 : 0
  setTopTen(value)
  buildNodes()
})

$(".red-button").click(function() {
  if (PRIORITIES.indexOf('red') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('red'), 1)
  var toggle = $(".red-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
  } else {
    PRIORITIES.push('red')
    toggle.data('value', 1)
  }
  updateToggleButton(toggle)
  setTopTen(0)
  buildNodes()
})
$(".amber-button").click(function() {
  if (PRIORITIES.indexOf('amber') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('amber'), 1)
  var toggle = $(".amber-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
  } else {
    PRIORITIES.push('amber')
    toggle.data('value', 1)
  }
  updateToggleButton(toggle)
  setTopTen(0)
  buildNodes()
})
$(".yellow-button").click(function() {
  if (PRIORITIES.indexOf('yellow') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('yellow'), 1)
  var toggle = $(".yellow-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
  } else {
    PRIORITIES.push('yellow')
    toggle.data('value', 1)
  }
  updateToggleButton(toggle)
  setTopTen(0)
  buildNodes()
})
$(".green-button").click(function() {
  if (PRIORITIES.indexOf('green') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('green'), 1)
  var toggle = $(".green-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
  } else {
    PRIORITIES.push('green')
    toggle.data('value', 1)
  }
  updateToggleButton(toggle)
  setTopTen(0)
  buildNodes()
})

$('.graph-display').click(function() {
  if ($(this).data('value') == 'dynamic') {
    $(this).data('value', 'static')
    $(this).text('Switch to dynamic view')
  } else {
    $(this).data('value', 'dynamic')
    $(this).text('Switch to static view')
  }
  $('#mynetwork').toggle()
  $('#staticnetwork').toggle()
});

})

