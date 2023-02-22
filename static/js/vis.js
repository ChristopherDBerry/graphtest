var NODES = new vis.DataSet([])
var EDGES = new vis.DataSet([])

var DISTANCE = 3

var PRIORITIES = ['red', 'amber', 'yellow', 'green']

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
  var nodes = ALL_ELEMENTS.nodes.filter(function(x) {
    return x.group === 'cluster' || (x.distance <= DISTANCE &&
      PRIORITIES.indexOf(x.group) > -1 )
  })
  //XXX reorder nodes
  ACTIVE_ELEMENTS.nodes.clear()
  ACTIVE_ELEMENTS.nodes.add(nodes)
  redrawMain()
  var static_results = $('.static-results-table tbody')
  static_results.empty()
  nodes.forEach(function (node, index) {
    console.log(node)
    var row = $('<tr>')
    var cell = $('<td>') //icon
    cell.appendTo(row)
    cell = $('<td>').text(node.url) //XXX title or url
    cell.appendTo(row)
    cell = $('<td>') //wcag
    cell.appendTo(row)
    cell = $('<td>') //axe
    cell.appendTo(row)
    cell = $('<td>') //content editot
    cell.appendTo(row)
    cell = $('<td>') //recheck
    cell.appendTo(row)
    row.appendTo(static_results)
  });
}

$(function() {

$("#distance1").click(function() {
  DISTANCE = 1
  buildNodes()
})
$("#distance2").click(function() {
  DISTANCE = 2
  buildNodes()
})
$("#distance3").click(function() {
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
  console.log(ALL_ELEMENTS)
  redrawMain()
  $("#chart-loading").hide()
  $(".expand-horizontal-icon").show()
  $("#settings-header").show()
  $("#chart-controls").show()
})

$(".red-button").click(function() {
  if (PRIORITIES.indexOf('red') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('red'), 1)
  var toggle = $(".red-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
    toggle.addClass('empty-toggle')
  } else {
    PRIORITIES.push('red')
    toggle.data('value', 1)
    toggle.removeClass('empty-toggle')
  }
  buildNodes()
})
$(".amber-button").click(function() {
  if (PRIORITIES.indexOf('amber') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('amber'), 1)
  var toggle = $(".amber-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
    toggle.addClass('empty-toggle')
  } else {
    PRIORITIES.push('amber')
    toggle.data('value', 1)
    toggle.removeClass('empty-toggle')
  }
  buildNodes()
})
$(".yellow-button").click(function() {
  if (PRIORITIES.indexOf('yellow') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('yellow'), 1)
  var toggle = $(".yellow-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
    toggle.addClass('empty-toggle')
  } else {
    PRIORITIES.push('yellow')
    toggle.data('value', 1)
    toggle.removeClass('empty-toggle')
  }
  buildNodes()
})
$(".green-button").click(function() {
  if (PRIORITIES.indexOf('green') > -1)
    PRIORITIES.splice(PRIORITIES.indexOf('green'), 1)
  var toggle = $(".green-button")
  if (toggle.data('value') === 1) {
    toggle.data('value', 0)
    toggle.addClass('empty-toggle')
  } else {
    PRIORITIES.push('green')
    toggle.data('value', 1)
    toggle.removeClass('empty-toggle')
  }
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

