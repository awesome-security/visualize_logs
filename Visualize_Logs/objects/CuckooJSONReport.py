#
# Includes
#

# NetworkX
import networkx

# OS
import os

# Pandas
import pandas

# Plotly
from plotly.offline import plot
from plotly.graph_objs import Bar, Scatter, Figure, Layout, \
    Line, Marker, Annotations, Annotation, XAxis, YAxis

# Regular Expressions
import re

# JSON
import json

# Exceptions
from . import Exceptions

#
# Classes
#


class CuckooJSONReport(object):
    """
    Class to hold Cuckoo-Modified JSON reports.

    https://github.com/spender-sandbox/cuckoo-modified
    """
    jsonreportfile = None
    """The JSON report file path."""

    jsonreportdata = None
    """This holds the actual data of the JSON report."""

    DiGraph = None
    """This holds the Networkx digraph to be plotted."""

    graphvizprog = None
    """This is the graphviz program used to generate the layout."""

    nodemetadata = dict()
    """This is a dict that will hold dicts of metadata for each node."""

    edgemetadata = dict()
    """This is a dict of (edge1,edge2) that will hold dicts of metadata
    for each edge."""

    rootpid = None
    """This is the pid (Node) on top."""

    def __init__(self, jsonreportfile=None):
        """
        The JSON report file is read and parsed using this class.  This
        could take a whiel depending on how big your JSON report is.

        This has been tested with the cuckoo-modifed version, but it may
        work with Cuckoo (proper) as well.

        :param jsonreportfile: The path to the JSON report file.
        :type jsonreportfile: A string.
        :returns: An object.
        :rtype: CuckooJSONReport object.
        """
        if not os.path.exists(jsonreportfile):
            raise Exceptions.VisualizeLogsInvalidFile(jsonreportfile)
        else:
            self.jsonreportfile = jsonreportfile

        with open(self.jsonreportfile, 'r') as jsonfile:
            self.jsonreportdata = json.load(jsonfile)

        # Create a network graph...
        self.digraph = networkx.DiGraph()

        # Add all the processes to the graph...
        self._add_all_processes()

    def _add_all_processes(self):
        """
        Internal function to add processess from JSON report
        process tree.

        :returns: Nothing.
        """
        self._processtree = self.jsonreportdata['behavior']['processtree']
        self._processes = self.jsonreportdata['behavior']['processes']

        self.rootpid = "PID {0}".format(self._processtree[0]['pid'])

        for process in self._processtree:
            self._add_processes_recursive(process)

        # Add the rest of the metadata...
        self._add_process_metadata()

    def _add_processes_recursive(self, processtreedict):
        """
        Internal function to add processes recursively from
        a dict representing the JSON process tree.

        :param processtreedict:  A dict of data from the process tree.
        :returns: Nothing.
        """
        pid = processtreedict['pid']
        ppid = processtreedict['parent_id']
        nodename = "PID {0}".format(pid)
        ppid_node = "PID {0}".format(ppid)

        self.digraph.add_node(nodename,
                              type='PID',
                              pid=pid,
                              parent_id=ppid)

        self.nodemetadata[nodename] = dict()
        self.nodemetadata[nodename]['node_type'] = 'PID'
        self.nodemetadata[nodename]['pid'] = pid
        self.nodemetadata[nodename]['parent_id'] = ppid
        self.nodemetadata[nodename]['threads'] = processtreedict['threads']
        self.nodemetadata[nodename]['environ'] = processtreedict['environ']
        self.nodemetadata[nodename]['name'] = processtreedict['name']
        self.nodemetadata[nodename]['module_path'] =\
            processtreedict['module_path']
        self.nodemetadata[nodename]['children'] = list()

        if ppid_node not in self.nodemetadata:
            self.nodemetadata[ppid_node] = dict()
            self.nodemetadata[ppid_node]['children'] = list()
            self.nodemetadata[ppid_node]['cmdline'] = ""

        self.nodemetadata[ppid_node]['children'].append(nodename)

        if ppid_node in self.digraph:
            self.digraph.add_edge(ppid_node, nodename)

        for child in processtreedict['children']:
            self._add_processes_recursive(child)

    def _add_process_metadata(self):
        """
        Internal function that ties the extra process metadata
        to the nodemetadata dict.

        :returns: Nothing.
        """
        for process in self._processes:
            nodename = "PID {0}".format(process['process_id'])
            self.nodemetadata[nodename]['first_seen'] = process['first_seen']
            self.nodemetadata[nodename]['calls'] =\
                pandas.DataFrame(process['calls'])

            calls = self.nodemetadata[nodename]['calls']

            createprocs = calls[calls['api'] == 'CreateProcessInternalW']

            for i, createproc in createprocs.iterrows():
                childpid = None
                cmdline = None
                for arg in createproc['arguments']:
                    if arg['name'] == 'ProcessId':
                        childpid = arg['value']
                    if arg['name'] == 'CommandLine':
                        cmdline = arg['value']

                if cmdline is None:
                    cmdline = "Not Available"

                if childpid is not None:
                    childnode = "PID {0}".format(childpid)
                    self.nodemetadata[childnode]['cmdline'] = cmdline

    def _create_positions_digraph(self):
        """
        Internal function to create the positions of the graph.

        :returns: Nothing.
        """

        # Create the positions...
        if self.graphvizprog is None:
            #  self.pos = networkx.fruchterman_reingold_layout(self.digraph)
            self.pos = networkx.spring_layout(self.digraph)
            # self.pos = networkx.circular_layout(self.digraph)
            # self.pos = networkx.shell_layout(self.digraph)
            # self.pos = networkx.spectral_layout(self.digraph)
        else:
            self.pos = \
                networkx.drawing.nx_pydot.graphviz_layout(
                    self.digraph, prog=self.graphvizprog,
                    root=self.rootpid)

    def _generategraph(self):
        """
        Internal function to create the output data for plotly.

        :returns: The data that can be plotted with plotly scatter
            plots.
        """

        # Node coordinates...
        ProcessX = []
        ProcessY = []

        # Edge coordinates...
        ProcessXe = []
        ProcessYe = []

        # Hover Text...
        proctxt = []

        for node in self.digraph:
            if self.digraph.node[node]['type'] == 'PID':
                ProcessX.append(self.pos[node][0])
                ProcessY.append(self.pos[node][1])
                if 'cmdline' in self.nodemetadata[node]:
                    cmdline = self.nodemetadata[node]['cmdline']
                else:
                    cmdline = "Not Available"
                proctxt.append(
                    "PID: {0}<br>"
                    "Path: {1}<br>"
                    "Command Line: {2}<br>"
                    "Parent PID: {3}"
                    .format(
                        self.nodemetadata[node]['pid'],
                        self.nodemetadata[node]['module_path'],
                        cmdline,
                        self.nodemetadata[node]['parent_id']
                        )
                               )
        for edge in self.digraph.edges():
            if (self.digraph.node[edge[0]]['type'] == 'PID' and
                    self.digraph.node[edge[1]]['type'] == 'PID'):
                ProcessXe.append(self.pos[edge[0]][0])
                ProcessXe.append(self.pos[edge[1]][0])
                ProcessXe.append(None)
                ProcessYe.append(self.pos[edge[0]][1])
                ProcessYe.append(self.pos[edge[1]][1])
                ProcessYe.append(None)

        nodes = []
        edges = []

        # PROCESSES...

        marker = Marker(symbol='circle', size=10)

        # Create the nodes...
        ProcNodes = Scatter(x=ProcessX,
                            y=ProcessY,
                            mode='markers',
                            marker=marker,
                            name='Process',
                            text=proctxt,
                            hoverinfo='text')

        # Create the edges for the nodes...
        ProcEdges = Scatter(x=ProcessXe,
                            y=ProcessYe,
                            mode='lines',
                            line=Line(shape='linear'),
                            name='Process Start',
                            hoverinfo='none')

        nodes.append(ProcNodes)
        edges.append(ProcEdges)

        # Reverse the order and mush...
        output = []
        output += edges[::-1]
        output += nodes[::-1]

        # Return the plot data...
        return output

    def _generateannotations(self):
        """
        Internal function to generate annotations on the graph.

        :returns: A list of annotations for plotly.
        """
        annotations = Annotations()

        for node in self.digraph:
            if self.digraph.node[node]['type'] == 'PID':
                annotations.append(
                    Annotation(
                        text="{0}<br>PID: {1}".format(
                            self.nodemetadata[node]['name'],
                            self.nodemetadata[node]['pid']
                            ),
                        x=self.pos[node][0],
                        y=self.pos[node][1],
                        xref='x',
                        yref='y',
                        showarrow=True,
                        ax=-40,
                        ay=-40
                        )
                    )

        return annotations

    def plotgraph(self,
                  graphvizprog='dot',
                  filename='temp-plot.html',
                  title=None, auto_open=True,
                  image=None, image_filename='plot_image',
                  image_height=600, image_width=800):
        """

        Function to plot the graph of the ProcMon CSV.

        :param graphvizprog: The graphviz program to use for layout, valid
            options are 'dot', 'neato', 'twopi', 'circo', 'fdp',
            'sfdp', 'patchwork', and 'osage'.  Graphviz is REQUIRED to be
            installed and in your path to use this library!  The associated
            layout programs must be available in your path as well.  More
            information for the layout types can be found here:
            http://www.graphviz.org/Documentation.php
            If this value is None, the internal networkx layout algorithms
            will be used.
        :param filename: A file name for the interactive HTML plot.
        :param title: A title for the plot.
        :param auto_open: Set to false to not open the file in a web browser.
        :param image: An image type of 'png', 'jpeg', 'svg', 'webp', or None.
        :param image_filename: The file name for the exported image.
        :param image_height: The number of pixels for the image height.
        :param image_width: The number of pixels for the image width.
        :returns: Nothing

        """
        self.graphvizprog = graphvizprog

        # Layout the positions...
        self._create_positions_digraph()

        outputdata = self._generategraph()
        annotations = self._generateannotations()

        # Hide axis line, grid, ticklabels and title...
        axis = dict(showline=False,
                    zeroline=False,
                    showgrid=False,
                    showticklabels=False,
                    title='')

        plotlayout = Layout(showlegend=True, title=title,
                            xaxis=XAxis(axis),
                            yaxis=YAxis(axis),
                            hovermode='closest',
                            annotations=annotations)

        plotfigure = Figure(data=outputdata,
                            layout=plotlayout)

        # Plot without the plotly annoying link...
        plot(plotfigure, show_link=False, filename=filename,
             auto_open=auto_open, image=image,
             image_filename=image_filename,
             image_height=image_height,
             image_width=image_width)
